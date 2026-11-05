# Galaxy History Evaluator overview

| Student | Tutorial | History | Step score | Final result | In short | Report |
|---|---|---|---|---|---|---|
{%- for row in rows %}
{%- if row.error %}
| {{ row.student | replace("|", "\\|") }} | {{ row.tutorial | replace("|", "\\|") }} | [{{ row.history_id or "history" }}]({{ row.history }}) | | | ❌ Could not be evaluated: {{ row.error | replace("|", "\\|") | replace("\n", " ") }} | |
{%- else %}
| {{ row.student | replace("|", "\\|") }} | {{ row.tutorial | replace("|", "\\|") }} | [{{ row.history_id or "history" }}]({{ row.history }}) | {{ row.score.steps }} % | {% if row.score.final_output is not none %}{{ row.score.final_output }} %{% endif %} | {% if row.score.all_steps_from_history or row.score.copied_steps %}⚠️ {% endif %}{{ row.in_short | join(" ") | replace("|", "\\|") }} | [report]({{ row.report }}) |
{%- endif %}
{%- endfor %}

{{ score_explanation }}
