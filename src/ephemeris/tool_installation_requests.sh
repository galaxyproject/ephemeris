#!/usr/bin/env bash
# Opens an issue or a pull request in this repository for each new tool
# installation request on a Galaxy server, and tells the requester where it is
# handled. Once the issue or pull request is closed, it tells them whether the
# tools got installed. Run it on a schedule with `consume-tool-installation-requests
# run`, from any CI system or cron, in a clean checkout of the repository, on a
# machine that can reach Galaxy. See the consume-tool-installation-requests page
# of the ephemeris docs.
#
# It needs bash 4.4 or later, git, curl and jq, and reads these variables:
#
# EPHEMERIS_GALAXY   Galaxy server.
# EPHEMERIS_API_KEY  API key of a Galaxy admin account.
# FORGE_TOKEN        Token that may push branches and open issues and pull requests.
# FORGE              github or gitlab. Found out in GitHub Actions and GitLab CI.
# FORGE_API          REST API URL. Found out in GitHub Actions and GitLab CI, and
#                    https://api.github.com for GitHub elsewhere.
# FORGE_PROJECT      owner/name on GitHub, project ID or path on GitLab. Found out
#                    in GitHub Actions and GitLab CI.
# PUSH_URL           Where to push branches (default: origin, or the project URL
#                    in GitLab CI, whose origin only allows fetching).
# TOOLS_FILE         Tool list that pull requests add tools to.
# APPLY_COMMAND      Shell command that adds the tools of the work item in the file
#                    $ITEM to the checkout, for repositories that are not a single
#                    tool list. Defaults to render-yaml into TOOLS_FILE.
# EMIT_OPTIONS       More options for emit, written as in a shell, for example
#                    --panel-label 'Other Tools' --pin-latest.
# REQUEST_LABEL      Label of the issues and pull requests opened here
#                    (default: tool installation request).
# ANSWERED_LABEL     Label added once the requester got told how their request
#                    ended (default: tool installation request answered).
#
# Without TOOLS_FILE or APPLY_COMMAND, every request becomes an issue. Pull
# requests go to the checked out branch.
set -euo pipefail

if [ -z "${FORGE:-}" ]; then
    if [ "${GITHUB_ACTIONS:-}" = true ]; then
        FORGE=github
    elif [ "${GITLAB_CI:-}" = true ]; then
        FORGE=gitlab
    fi
fi
case "${FORGE:-}" in
github)
    FORGE_API=${FORGE_API:-${GITHUB_API_URL:-https://api.github.com}}
    FORGE_PROJECT=${FORGE_PROJECT:-${GITHUB_REPOSITORY:-}}
    git_user=x-access-token
    ;;
gitlab)
    FORGE_API=${FORGE_API:-${CI_API_V4_URL:-}}
    FORGE_PROJECT=${FORGE_PROJECT:-${CI_PROJECT_ID:-}}
    git_user=oauth2
    if [ -z "${PUSH_URL:-}" ] && [ -n "${CI_SERVER_URL:-}" ]; then
        # GitLab CI makes git use the job token, which may not push, for URLs of its server.
        # It leaves a URL that names a user alone, so git asks the credential helper below.
        PUSH_URL="${CI_SERVER_URL/:\/\//://$git_user@}/$CI_PROJECT_PATH.git"
    fi
    ;;
*)
    echo "Set FORGE to github or gitlab" >&2
    exit 1
    ;;
esac
: "${FORGE_TOKEN:?}" "${FORGE_API:?}" "${FORGE_PROJECT:?}"
PUSH_URL=${PUSH_URL:-origin}
# GitLab CI checks out a commit rather than a branch.
base_branch=${CI_COMMIT_BRANCH:-$(git branch --show-current)}
: "${base_branch:?Check out the branch that pull requests go to}"
REQUEST_LABEL=${REQUEST_LABEL:-tool installation request}
ANSWERED_LABEL=${ANSWERED_LABEL:-tool installation request answered}
if [ -z "${APPLY_COMMAND:-}" ] && [ -n "${TOOLS_FILE:-}" ]; then
    # shellcheck disable=SC2016 # expanded when the command runs
    APPLY_COMMAND='jq -s . "$ITEM" | consume-tool-installation-requests render-yaml --tools-file "$TOOLS_FILE" -o "$TOOLS_FILE"'
fi
export FORGE_TOKEN TOOLS_FILE
# Commit as the person configured in git, or else as this script.
git_identity=()
if ! git config user.email > /dev/null; then
    git_identity=(-c "user.name=Tool installation requests" -c "user.email=tool-installation-requests@localhost")
fi
emit_options=()
eval "emit_options=(${EMIT_OPTIONS:-})"

# Pull requests commit every change that APPLY_COMMAND makes.
if [ -n "$(git status --porcelain)" ]; then
    echo "Run this in a clean checkout" >&2
    exit 1
fi
base=$(git rev-parse HEAD)
start=$(git symbolic-ref --quiet --short HEAD || echo "$base")
work=$(mktemp -d)
# Leave the checkout on the branch it was on, which the next run starts from.
trap 'git checkout --quiet --force "$start"; git clean --quiet --force -d; rm -rf "$work"' EXIT

requests() { consume-tool-installation-requests "$@"; }
uri() { jq -rn --arg value "$1" '$value | @uri'; }

headers() {
    if [ "$FORGE" = github ]; then
        printf '%s\n' "Authorization: Bearer $FORGE_TOKEN" "Accept: application/vnd.github+json"
    else
        printf '%s\n' "PRIVATE-TOKEN: $FORGE_TOKEN"
    fi
    echo "Content-Type: application/json"
}

# api METHOD PATH [JSON_FILE] prints the response to a request about this repository.
api() {
    local status
    # Headers come from a file, so that the token stays out of the process list.
    status=$(curl --silent --show-error --max-time 300 --output "$work/response.json" --write-out '%{http_code}' \
        --request "$1" --header @<(headers) ${3:+--data-binary "@$3"} "$FORGE_API/$project$2") || return 1
    # Callers in a subshell read the status from here.
    echo "$status" > "$work/status"
    if [ "$status" -ge 300 ]; then
        echo "$1 $2 failed with HTTP $status: $(head -c 500 "$work/response.json")" >&2
        return 1
    fi
    cat "$work/response.json"
}

# list PATH FILTER adds what jq's FILTER makes of every page of PATH to artifacts.jsonl.
list() {
    local page
    for ((page = 1; ; page++)); do
        api GET "$1&per_page=100&page=$page" > "$work/page.json"
        [ "$(jq length "$work/page.json")" -gt 0 ] || break
        jq -c ".[] | $2" "$work/page.json" >> "$work/artifacts.jsonl"
    done
}

# Turns an issue or pull request into {url, number, kind, state, labels, created_at, closed_at, id}.
# shellcheck disable=SC2016 # a jq expression
artifact='{url, number, kind, state, labels, created_at, closed_at,
    id: ((.body // "" | split("\n")[0] // "" | capture("notification `(?<id>[^`]+)`") | .id) // null)}'

if [ "$FORGE" = github ]; then
    project="repos/$FORGE_PROJECT"
    label_color=ededed

    # Lists the issues and pull requests that have the label, which GitHub returns together.
    list_artifacts() {
        list "/issues?state=all&labels=$(uri "$REQUEST_LABEL")" "{
            url: .html_url, number, body, created_at, labels: [.labels[].name],
            kind: (if .pull_request then \"change\" else \"issue\" end),
            state: (if .pull_request.merged_at then \"merged\" elif .state == \"closed\" then \"closed\" else \"open\" end),
            closed_at: (.pull_request.merged_at // .closed_at)} | $artifact"
    }

    # Prints the URL and number of a pull request from this repository's branch $1, open or not.
    find_change() {
        api GET "/pulls?state=all&head=$(uri "${FORGE_PROJECT%%/*}:$1")" |
            jq -r '.[0] | select(.) | "\(.html_url) \(.number)"'
    }

    # add_label KIND NUMBER LABEL
    add_label() {
        jq -n --arg name "$3" '{labels: [$name]}' > "$work/label-payload.json"
        api POST "/issues/$2/labels" "$work/label-payload.json" > /dev/null
    }

    open_change() {
        jq -n --arg head "$1" --arg base "$base_branch" --arg title "$2" --rawfile body "$work/body.md" \
            '{$head, $base, $title, $body}' > "$work/payload.json"
        api POST /pulls "$work/payload.json" > "$work/change.json" || return 1
        # A later run labels it if this fails, when it finds the pull request by its branch.
        add_label change "$(jq -r .number "$work/change.json")" "$REQUEST_LABEL" || true
        jq -r .html_url "$work/change.json"
    }

    open_issue() {
        jq -n --arg title "$1" --rawfile body "$work/body.md" --arg name "$REQUEST_LABEL" \
            '{$title, $body, labels: [$name]}' > "$work/payload.json"
        api POST /issues "$work/payload.json" | jq -r .html_url
    }
else
    project="projects/$(uri "$FORGE_PROJECT")"
    label_color='#ededed'

    list_artifacts() {
        list "/issues?state=all&labels=$(uri "$REQUEST_LABEL")" "{
            url: .web_url, number: .iid, body: .description, created_at, closed_at, labels, kind: \"issue\",
            state: (if .state == \"closed\" then \"closed\" else \"open\" end)} | $artifact"
        list "/merge_requests?state=all&labels=$(uri "$REQUEST_LABEL")" "
            select(.source_project_id == .target_project_id) | {
            url: .web_url, number: .iid, body: .description, created_at, labels, kind: \"change\",
            state: (if .state == \"merged\" or .state == \"closed\" then .state else \"open\" end),
            closed_at: (.merged_at // .closed_at)} | $artifact"
    }

    # Prints the URL and number of a merge request from this project's branch $1, open or not.
    find_change() {
        api GET "/merge_requests?state=all&source_branch=$(uri "$1")" |
            jq -r 'map(select(.source_project_id == .target_project_id))[0] | select(.) | "\(.web_url) \(.iid)"'
    }

    add_label() {
        local path=issues
        [ "$1" = change ] && path=merge_requests
        jq -n --arg labels "$3" '{add_labels: $labels}' > "$work/label-payload.json"
        api PUT "/$path/$2" "$work/label-payload.json" > /dev/null
    }

    open_change() {
        jq -n --arg source_branch "$1" --arg target_branch "$base_branch" --arg title "$2" \
            --rawfile description "$work/body.md" --arg labels "$REQUEST_LABEL" \
            '{$source_branch, $target_branch, $title, $description, $labels, remove_source_branch: true}' \
            > "$work/payload.json"
        api POST /merge_requests "$work/payload.json" | jq -r .web_url
    }

    open_issue() {
        jq -n --arg title "$1" --rawfile description "$work/body.md" --arg labels "$REQUEST_LABEL" \
            '{$title, $description, $labels}' > "$work/payload.json"
        api POST /issues "$work/payload.json" | jq -r .web_url
    }
fi

push() {
    # The credential helper reads the token from the environment when git asks for it.
    git -c credential.helper= \
        -c "credential.helper=!f() { echo username=$git_user; echo \"password=\$FORGE_TOKEN\"; }; f" \
        push --quiet --force "$PUSH_URL" "HEAD:refs/heads/$1"
}

# Opens an issue or a pull request for the work item, unless an earlier run did, and tells the requester.
handle() {
    local id action title branch url found number
    # Without the newline that jq -r adds, which a body at GitHub's limit has no room for.
    jq -j .body "$work/item.json" > "$work/body.md"
    { read -r id; read -r action; read -r title; } < <(jq -r '.notification_id, .action, .title' "$work/item.json")
    branch="tool-request/$id"
    # Reuse what an earlier run opened, also if the request turned from an issue into a pull request since.
    url=$(jq -rn --arg id "$id" 'first(inputs | select(.id == $id) | .url) // empty' "$work/artifacts.jsonl")
    if [ -z "$url" ]; then
        found=$(find_change "$branch") || return 1
        read -r url number <<< "$found"
        if [ -n "$url" ]; then
            # Without the label, later runs would not know the request is handled, and tell the requester again.
            add_label change "$number" "$REQUEST_LABEL" || echo "Could not label $url" >&2
        fi
    fi
    if [ -z "$url" ] && [ "$action" = pr ] && [ -n "${APPLY_COMMAND:-}" ]; then
        git switch --quiet -C "$branch" "$base" || return 1
        ITEM="$work/item.json" bash -eo pipefail -c "$APPLY_COMMAND" || return 1
        git add --all || return 1
        # Without changes, the repository has these tools already, so an admin looks at the request in an issue.
        if ! git diff --cached --quiet; then
            git "${git_identity[@]}" commit --quiet --message "$title" || return 1
            push "$branch" || return 1
            if ! url=$(open_change "$branch" "$title"); then
                # For example, GitHub Actions may not be allowed to open pull requests.
                [ "$(cat "$work/status")" = 403 ] || return 1
                echo "Not allowed to open a pull request for $id, so opening an issue" >&2
            fi
        fi
    fi
    if [ -z "$url" ]; then
        url=$(open_issue "$title") || return 1
    fi
    requests reply --notification-id "$id" --url "$url" && requests mark-seen "$id"
}

# Tells the requester whether the tools of a closed issue or pull request got installed.
tell_outcome() {
    local id url number kind state answer
    { read -r id; read -r url; read -r number; read -r kind; read -r state; } \
        < <(jq -r '.id, .url, .number, .kind, .state' "$work/artifact.json")
    answer=$(requests installed --notification-id "$id") || return 1
    if [ "$answer" = yes ]; then
        state=installed
    elif [ "$state" = merged ]; then
        # Wait for the tools to be installed.
        return 0
    else
        state=closed
    fi
    requests reply --notification-id "$id" --url "$url" --state "$state" &&
        add_label "$kind" "$number" "$ANSWERED_LABEL"
}

# Make sure the labels exist. Creating one that exists fails harmlessly.
for label in "$REQUEST_LABEL" "$ANSWERED_LABEL"; do
    jq -n --arg name "$label" --arg color "$label_color" '{$name, $color}' > "$work/label.json"
    api POST /labels "$work/label.json" > /dev/null 2>&1 || true
done

# Listing by label, unlike searching, sees what was opened a few seconds ago.
: > "$work/artifacts.jsonl"
list_artifacts
jq -r 'select(.id) | .id' "$work/artifacts.jsonl" > "$work/handled.txt"
# Requests sent since the first issue or pull request are handled here even if an admin read them in Galaxy.
since=$(jq -rn '[inputs | select(.id) | .created_at] | min // empty' "$work/artifacts.jsonl")

failed=0
# EMIT_OPTIONS come last, so that a --seen-since there wins.
requests emit --handled "$work/handled.txt" ${since:+--seen-since "$since"} "${emit_options[@]}" |
    jq -c '.[]' > "$work/requests.jsonl"
while read -r line <&3; do
    printf '%s\n' "$line" > "$work/item.json"
    if ! handle; then
        echo "Request $(jq -r .notification_id "$work/item.json") failed, the next run tries again" >&2
        failed=1
    fi
    git switch --quiet --discard-changes --detach "$base"
    git clean --quiet --force -d
done 3< "$work/requests.jsonl"

# Tell each request's outcome once, from a merged pull request if it has one, else from what was closed last.
# A request that still has an open issue or pull request is not over yet. GitHub's label names ignore case.
jq -c -s --arg answered "$ANSWERED_LABEL" '
    group_by(.id)[]
    | select(.[0].id and all(.[]; .state != "open")
        and ([.[].labels[] | ascii_downcase] | index($answered | ascii_downcase) | not))
    | (map(select(.state == "merged")) | max_by(.closed_at)) // max_by(.closed_at)' \
    "$work/artifacts.jsonl" > "$work/over.jsonl"
# Only look at what was closed in the last 30 days, so that pull requests whose tools never get installed are
# not looked up forever.
cutoff=$(jq -rn 'now - 30 * 86400 | todate')
jq -c --arg cutoff "$cutoff" 'select((.closed_at // "") >= $cutoff)' "$work/over.jsonl" > "$work/closed.jsonl"
expired=$(jq -r --arg cutoff "$cutoff" 'select(.state == "merged" and (.closed_at // "") < $cutoff) | .url' \
    "$work/over.jsonl" | tr '\n' ' ')
if [ -n "$expired" ]; then
    echo "Stopped waiting for the tools of these pull requests, merged over 30 days ago, so their requesters were" \
        "not told. Add the label \"$ANSWERED_LABEL\" to them to stop this warning: ${expired% }" >&2
fi
while read -r line <&3; do
    printf '%s\n' "$line" > "$work/artifact.json"
    if ! tell_outcome; then
        echo "Could not tell the requester about $(jq -r .url "$work/artifact.json"), the next run tries again" >&2
        failed=1
    fi
done 3< "$work/closed.jsonl"
exit "$failed"
