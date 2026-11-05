Galaxy-history-eval
===================

.. automodule :: ephemeris.history_evaluator.cli

Usage
-----

.. argparse::
   :module: ephemeris.history_evaluator.cli
   :func: parser
   :prog: galaxy-history-eval

Examples
~~~~~~~~

Compare a history to the workflow of a `GTN <https://training.galaxyproject.org/>`_ tutorial:

.. code-block:: bash

    $ galaxy-history-eval \
        -u "https://usegalaxy.eu/histories/view?id=19b7e0ced2125767" \
        -w "https://training.galaxyproject.org/training-material/topics/introduction/tutorials/galaxy-intro-short/workflows/Galaxy-Workflow-galaxy-intro-short.ga" \
        -o report

Compare a history to a reference history, e.g. the tutor's own run of the tutorial:

.. code-block:: bash

    $ galaxy-history-eval \
        -u "https://usegalaxy.eu/histories/view?id=892319be4e2b6ca2" \
        -r "https://usegalaxy.eu/histories/view?id=c1ad4cd9d7df4ada" \
        -o report

Compare a history shared only with your account (not published):

.. code-block:: bash

    $ galaxy-history-eval -u "https://usegalaxy.eu/histories/view?id=..." -r "https://usegalaxy.eu/histories/view?id=..." -a $GALAXY_API_KEY -o report

On another Galaxy server, give the server with ``-g`` so the key is sent to it:

.. code-block:: bash

    $ galaxy-history-eval -g https://usegalaxy.org -u "https://usegalaxy.org/histories/view?id=..." -w workflow.ga -a $GALAXY_API_KEY


Several histories
~~~~~~~~~~~~~~~~~

Several histories can be evaluated at once with a CSV file (``-c``), e.g. all participants of a training:

.. code-block:: bash

    $ galaxy-history-eval -c histories.csv -a $GALAXY_API_KEY -o reports

The CSV file has one row per history, with these columns (in any order, case does not matter):

=================== ====================== ===============================================================
Column              Other accepted name    Content
=================== ====================== ===============================================================
``student name``    ``student``            name of the student, used for the folder of the reports
``stud hist id``    ``student_history``    id or link of the history to evaluate
``ref hist id``     ``ref_history``        id or link of the reference history, or link of a workflow
``tutorial name``                          optional, shown in the overview and used for the folder
=================== ====================== ===============================================================

For example:

.. code-block:: text

    Tutorial name,Ref hist id,Stud hist id,Student name
    From Peaks to Genes,c1ad4cd9d7df4ada,892319be4e2b6ca2,Participant 1
    Galaxy intro,https://training.galaxyproject.org/training-material/topics/introduction/tutorials/galaxy-intro-short/workflows/Galaxy-Workflow-galaxy-intro-short.ga,19b7e0ced2125767,Participant 1

- History ids are on the Galaxy server given with ``-g``. Links can point to any server.
- Each row has its own reference, so one file can cover several tutorials. A reference is loaded once for all
  its rows. A reference that can not be loaded is tried only once: all its rows get the error.
- Files saved by Excel or Google Sheets work: separated by ``,``, ``;`` (e.g. German Excel) or tabs, in UTF-8 or
  Windows encoding. Rows without student, history or reference are skipped.
- A student can be in several rows, e.g. one per tutorial or several histories for the same tutorial. Each history
  gets its own row in the overview and its own folder: the folder is named after the student and the tutorial,
  with ``_2``, ``_3``, ... for the next histories with the same name. The **History** column of the overview links
  each history, so rows of the same student are told apart.
- A history that can not be evaluated (e.g. wrong link, not shared) gets an error in the overview, and the other
  histories are still evaluated.


Output
~~~~~~

For each history, the tool generates:

- ``report.html`` and ``report.md`` with a summary in plain sentences, the score, and the comparison of each
  reference step with the matched history step (tool, version, inputs, settings, output formats), the extra steps,
  copied steps and, with a reference history, the comparison of the final output
- ``report.json`` with all the details of the comparison

With a CSV file, the reports of each history are in their own folder, with ``overview.md`` and ``overview.json``
for all histories. ``overview.md`` is a table with, for each history: student, tutorial, history link, step score,
final result, the summary in plain sentences, and the link to the report. It is written after each history, so the
histories already evaluated are kept if the run is interrupted.

How the steps are matched, what counts as done and how the score is computed is explained below.


How it works
------------

The reference
~~~~~~~~~~~~~

The reference is either:

- **a workflow** (``-w``): a workflow file (``.ga``), e.g. the workflow of a tutorial of the
  `Galaxy Training Network <https://training.galaxyproject.org/>`_, or a Galaxy workflow link. Only the steps are compared.
- **a history** (``-r``): e.g. the tutor's own run of the tutorial. The steps are compared like with a workflow, and also
  the output formats of each step and the result of the last step.

A reference history is read the same way as the history to evaluate (see below). Steps the tutor threw away in the
reference history are not asked from the students:

- failed steps,
- attempts run again: all outputs deleted, not used by a later step, and another run of the same tool kept.

A deleted final result without another run of the tool is still asked: deleting a result to save space does not
make it an attempt.


Reading a history
~~~~~~~~~~~~~~~~~

A history is turned into a workflow without changing anything in Galaxy, with these API calls:

- ``/api/histories/{id}/extraction_summary``: the jobs and inputs of the history, as used by Galaxy to extract a workflow
  from a history. A step run over a collection (map over) is one step, even if a copied history lists it once per element.
- ``/api/jobs/{id}?full=true``: tool id and version, settings, inputs (to know which step each input comes from),
  history where the job ran, user who ran it, end time, state and job cache.
- ``/api/histories/{id}/contents`` and ``/api/dataset_collections/{id}``: which outputs are deleted, their formats,
  and the states of the datasets in output collections.

Histories have to be accessible to the account of the API key: shared with it, published, or shared via link. The API
key is only sent to the Galaxy server given with ``-g`` (https://usegalaxy.eu by default). Histories on other servers
are read without key.


Matching the steps
~~~~~~~~~~~~~~~~~~

Steps of the history are matched to the steps of the reference **by tool and by the steps their inputs come from**,
not by their order or position in the history. So:

- steps run in another order are found,
- a step run several times is found, and the run used by the next steps is compared,
- steps not in the reference are reported as extra steps,
- a different version of the same tool still matches.

The reference steps are taken in order. For each one, the history steps with the same tool are candidates, and the
chosen one is, in this order of priority:

1. the one with the most inputs coming from the steps already matched to the inputs of the reference step,
2. the one thrown away (or not) like the reference step,
3. the one with the most settings like the reference step,
4. the one whose outputs are used by other steps,
5. the one with the same tool version,
6. the one at the same position among the runs of the tool (e.g. the 2nd run with the 2nd run),
7. the one that finished last.

The data inputs (uploaded datasets and collections) are matched after the tool steps: each matched tool step votes for
the history input it used where the reference used an input. The input with the most votes wins, then the one with the
same datatype, then the one at the same position. So one step run on the wrong input does not change which input is
which. The remaining inputs are matched by order.


What counts as done
~~~~~~~~~~~~~~~~~~~

- A step whose job **failed or did not finish** (e.g. cancelled, still running) is not done. The report lists it as
  failed or not finished.
- A step run **over a collection** is failed only if all its elements failed. If only some failed, it is done and the
  report says how many elements failed.
- A step that **finished and was deleted** afterwards still counts as done, and the report flags it. Steps whose
  outputs were all deleted are not counted as extra steps.
- An **interactive tool** (e.g. Jupyter) counts as done when it was stopped, as stopping it ends its job.


Comparing the matched steps
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For each reference step and its matched history step, the report gives:

- **Tool version**: shown, but a different version does not lower the score.
- **Inputs**: whether each input comes from the matched step of the reference input, input by input. Swapped inputs
  (e.g. the two inputs of an intersect) are different.
- **Settings**: each setting of the reference step compared with the history step. Settings that depend on the server
  or the run (e.g. ``dbkey``, ``chromInfo``, job resources, job cache) and the names of collection elements are not
  compared. Data inputs are compared as inputs, not as settings.
- **Output formats** (reference history only).


Final result (reference history only)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The output of the last step of the reference (by job end time, without deleted or failed steps) is compared with the
outputs of the last 5 steps of the history. For text datasets, the content is compared line by line: the final result
is the similarity of the most similar output, between 0 and 100 %. Binary, purged or collection outputs are not compared.


Score
~~~~~

Every step of the reference is worth 100 points:

- 50 points if the step is done in the history,
- 25 more if it was run on the same inputs as in the reference,
- up to 25 more for the same settings: each setting counts the same, so 1 different setting out of 4 costs 6.25 points.

A missing step gets 0 points. The step score is the average over all steps of the reference. Thrown away steps of the
reference are not part of it. The final result is given separately and is not part of the step score.

For example, with a reference of 8 steps where 7 are done with the same inputs and settings and 1 is missing, the
step score is (7 x 100 + 0) / 8 = 87.5 %.


Warnings
~~~~~~~~

The report warns about results that were probably not produced by the student in this history:

- **Copied results**: steps whose job ran in another history, i.e. results copied from another history. The report
  says if the job was run by the owner of the history ("of the same user": copied from their own other history) or by
  "another user", without saying who. Steps whose job can not be read, usually because it ran in a private history of
  someone else, are reported as copied from a history that is not accessible. Copied steps still count as done in the
  score: the tutor decides what to do with them.
- **Copy of a whole history**: when no step ran in the history itself, the report says so and names the history where
  most steps ran, and whether its jobs were run by the same or another user. This is expected for a history imported
  by a tutor, not for a history shared by a student.
- **Job cache**: steps whose result was reused from an earlier job instead of running the tool again. The report also
  shows if the reference used the job cache for that step.

Who ran a job is only known on Galaxy servers whose job API returns the user of the job to the reader (e.g.
usegalaxy.eu). Otherwise the report only says that results were copied from another history.


Reports
~~~~~~~

For each history, the tool writes:

- ``report.html`` and ``report.md``:

  - **In short**: a few plain sentences: steps done and missing, other settings, other inputs, other output formats,
    extra steps, failed steps, copied results, job cache and final result.
  - **Summary**: the scores and numbers of steps, with an explanation of the score and of the icons (✅ same as the
    reference, ❌ different or missing, ⚠️ different tool version).
  - **Steps**: every step of the reference with the matched history step, the versions, the inputs, the settings
    that are different, and notes (job cache, failed collection elements, deleted outputs, copied from).
  - **Final output** (reference history only), **steps not in the reference** and **steps copied from another history**.

- ``report.json`` with all the details of the comparison, e.g. to process the results with another tool.

With a CSV file (``-c``), the reports of each history are written in their own folder, with ``overview.md`` and
``overview.json`` for all histories (see above).
