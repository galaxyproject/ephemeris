{%- macro yes(value) -%}{% if value %}✅{% else %}❌{% endif %}{%- endmacro -%}
{%- macro cell(value) -%}{{ (value if value is not none else "") | string | replace("|", "\\|") | replace("\n", " ") }}{%- endmacro -%}
# Galaxy History Evaluator report

- Galaxy history: {{ report.inputs.history }}
- Reference {{ report.inputs.reference_type or "workflow" }}: {{ report.inputs.workflow }}
{% if report.all_steps_from_history %}
> ⚠️ No step of this history ran in it, most steps ran in history {{ report.all_steps_from_history }}: the history is a copy of a whole history{% if report.all_steps_by %} ({{ report.all_steps_by }}){% endif %}. This is expected for a history imported by a tutor, not for a history shared by a student.
{% endif %}
{%- if report.in_short %}
## In short
{% for sentence in report.in_short %}
- {{ sentence }}
{%- endfor %}
{% endif %}
{%- if report.score %}
## Summary

| | |
|---|---|
| Step score | {{ report.score.steps }} % |
{%- if report.score.final_output is not none %}
| Final output similarity | {{ report.score.final_output }} % |
{%- endif %}
| Data inputs (reference / history) | {{ report.data_inputs.workflow }} / {{ report.data_inputs.history }} |
| Tool steps (reference / history) | {{ report.steps.workflow }} / {{ report.steps.history }} |
| Missing steps | {{ report.score.missing_steps }} |
| Extra steps (not deleted) | {{ report.score.extra_steps }} |
| Deleted steps | {{ report.score.deleted_steps }} |
| Failed or not finished steps | {{ report.score.failed_steps }} |
| Steps copied from another or a private history | {{ report.score.copied_steps }} |
| Steps from the job cache | {{ report.score.cached_steps }} |

{{ score_explanation }}

In the tables: ✅ same as the reference, ❌ different from the reference or missing, ⚠️ different tool version (does not lower the score).
{% endif %}
## Steps

| Reference step | Tool | History step | Version (reference / history) | Inputs from right steps | Wrong parameters | Notes |
|---|---|---|---|---|---|---|
{%- for step_num, s in report.comparison_given_reference_workflow_order.items() %}
{%- if s.status == "missing" %}
| {{ s.order.workflow }} | {{ cell(s.tool.workflow) }} | missing | {{ cell(s.version.workflow) }} | | | |
{%- else %}
| {{ s.order.workflow }} | {{ cell(s.tool.workflow) }} | {{ s.order.history }} | {{ cell(s.version.workflow) }} / {{ cell(s.version.history) }} {% if not s.version.same %}⚠️{% endif %} | {{ yes(s.inputs_connection.same) }} | {{ s.parameters.wrong }} / {{ s.parameters.number.workflow }} | {% if s.output_formats and not s.output_formats.same %}output formats {{ s.output_formats.history | join(", ") }} instead of {{ s.output_formats.workflow | join(", ") }}. {% endif %}{% if s.cached %}job cache{% if s.cached_reference %} (also in the reference){% endif %}. {% endif %}{% if s.failed_elements %}{{ s.failed_elements }} of {{ s.elements }} collection elements failed. {% endif %}{% if s.deleted %}outputs deleted. {% endif %}{% if s.copied_from_history %}copied from history {{ s.copied_from_history }}{% if s.copied_by %} ({{ s.copied_by }}){% endif %}.{% endif %} |
{%- endif %}
{%- endfor %}
{% for step_num, s in report.comparison_given_reference_workflow_order.items() %}
{%- set wrong = s.parameters.details.items() | rejectattr("1.same") | list %}
{%- if s.status != "missing" and wrong %}
### Step {{ s.order.workflow }} ({{ s.tool.workflow }}): different parameters

| Parameter | Reference | History |
|---|---|---|
{%- for key, value in wrong %}
| {{ cell(key) }} | {{ cell(value.workflow) }} | {{ cell(value.history) }} |
{%- endfor %}
{% endif %}
{%- endfor %}
{%- if report.final_outputs %}
## Final output

Last step of the reference: step {{ report.final_outputs.reference_step.order }}, {{ report.final_outputs.reference_step.tool }} ({{ report.final_outputs.reference_step.formats | join(", ") }}), compared to the last steps of the history.{% if report.final_outputs.note %} Note: {{ report.final_outputs.note }}.{% endif %}

| History step | Tool | Same tool | Same output formats | Content similarity |
|---|---|---|---|---|
{%- for c in report.final_outputs.candidates %}
| {{ c.order }} | {{ cell(c.tool) }} | {{ yes(c.same_tool) }} | {{ yes(c.formats.same) }} | {% if c.content_similarity is not none %}{{ (100 * c.content_similarity) | round(1) }} %{% else %}not compared{% endif %} |
{%- endfor %}
{% endif %}
{%- if report.extra_steps %}
## Steps not in the reference

| History step | Tool | Version | Job cache | Deleted | Failed |
|---|---|---|---|---|---|
{%- for s in report.extra_steps %}
| {{ s.order }} | {{ cell(s.tool) }} | {{ cell(s.version) }} | {% if s.cached %}yes{% endif %} | {% if s.deleted %}yes{% endif %} | {% if s.failed %}yes{% endif %} |
{%- endfor %}
{% endif %}
{%- if report.copied_steps %}
## Steps copied from another history

| History step | Tool | History where the job ran | Run by |
|---|---|---|---|
{%- for s in report.copied_steps %}
| {{ s.order }} | {{ cell(s.tool) }} | {{ s.history }} | {{ s.by or "unknown" }} |
{%- endfor %}
{% endif %}
