"""Direct tests of the Reporter, which the rest of the suite only exercises.

Every other test reaches the reporter through a checker run, so what it writes
and what it counts are only ever observed together and only in the combinations
the fixtures happen to produce. These pin down the pieces: the line formats, the
split between severities and categories, and the roll-up from a file's sub-total
to the run's total, which is the property the per-file footer and the synthesis
block both rest on.
"""

import io

import pytest

from isschecker.checker import Reporter


@pytest.fixture
def log():
    return io.StringIO()


def test_error_and_warning_line_formats(log):
    reporter = Reporter(log).category("naming")

    reporter.error("something is wrong.")
    reporter.warning("something is unusual.")
    reporter.ok("Something checked out: OK")
    reporter.note("Something else: N/A")

    assert log.getvalue() == (
        " - ERROR: something is wrong.\n"
        " - WARNING: something is unusual.\n"
        " - Something checked out: OK\n"
        " - Something else: N/A\n"
    )


def test_qualifier_labels_both_severities(log):
    reporter = Reporter(log).category("attr", qualifier="attributes")

    reporter.error("global attribute 'crs' is missing.")
    reporter.warning("coordinate 'time' on-disk dtype is float64.")

    assert log.getvalue() == (
        " - ERROR (attributes): global attribute 'crs' is missing.\n"
        " - WARNING (attributes): coordinate 'time' on-disk dtype is float64.\n"
    )


def test_bullet_is_configurable_for_experiment_level_findings(log):
    """Experiment-level findings are written flush left, not as list items."""
    reporter = Reporter(log).category("file", bullet="")

    reporter.error("In experiment historical, ... is (are) missing: ['lim']")

    assert log.getvalue() == (
        "ERROR: In experiment historical, ... is (are) missing: ['lim']\n"
    )


def test_ok_and_note_are_not_counted(log):
    reporter = Reporter(log)
    naming = reporter.category("naming")

    naming.ok("fine: OK")
    naming.note("not checked.")

    assert reporter.total_errors == 0
    assert reporter.total_warnings == 0


def test_warnings_are_counted_apart_from_errors(log):
    reporter = Reporter(log)
    naming = reporter.category("naming")

    naming.error("wrong.")
    naming.warning("unusual.")
    naming.warning("also unusual.")

    assert reporter.total_errors == 1
    assert reporter.total_warnings == 2
    assert reporter.error_count("naming") == 1
    assert reporter.warning_count("naming") == 2


def test_counts_are_kept_per_category(log):
    reporter = Reporter(log)

    reporter.category("time").error("wrong axis.")
    reporter.category("num").error("out of range.")
    reporter.category("num").error("also out of range.")
    reporter.category("attr").warning("unusual dtype.")

    assert reporter.error_count("time") == 1
    assert reporter.error_count("num") == 2
    assert reporter.error_count("attr") == 0
    assert reporter.warning_count("attr") == 1
    assert reporter.total_errors == 3
    assert reporter.total_warnings == 1


def test_a_count_reports_one_line_as_several_findings(log):
    """Four missing mandatory variables are one line and four errors."""
    reporter = Reporter(log)

    reporter.category("file", bullet="").error(
        "these mandatory variable(s) is (are) missing: ['a', 'b', 'c', 'd']",
        count=4,
    )

    assert log.getvalue().count("\n") == 1
    assert reporter.error_count("file") == 4


def test_child_sub_totals_roll_up_into_the_parent(log):
    """What a file's footer counts and what the synthesis counts are one thing."""
    run = Reporter(log)

    first_file = run.child()
    first_file.category("time").error("wrong axis.")
    first_file.category("attr").warning("unusual dtype.")

    second_file = run.child()
    second_file.category("num").error("out of range.")

    assert first_file.total_errors == 1
    assert first_file.total_warnings == 1
    assert second_file.total_errors == 1
    assert second_file.total_warnings == 0

    assert run.total_errors == 2
    assert run.total_warnings == 1
    assert run.error_count("time") == 1
    assert run.error_count("num") == 1
    assert run.warning_count("attr") == 1


def test_a_child_of_a_child_reaches_the_top(log):
    """The run, the experiment and the file are three levels, not two."""
    run = Reporter(log)
    experiment = run.child()
    file = experiment.child()

    file.category("spatial").error("bad corner.")

    assert file.total_errors == 1
    assert experiment.total_errors == 1
    assert run.total_errors == 1


def test_children_do_not_see_each_others_counts(log):
    run = Reporter(log)
    first = run.child()
    second = run.child()

    first.category("naming").error("wrong name.")

    assert second.total_errors == 0


def test_all_reporters_write_to_the_same_log(log):
    run = Reporter(log)

    run.child().category("naming").error("first.")
    run.child().category("time").warning("second.")

    assert log.getvalue() == (
        " - ERROR: first.\n"
        " - WARNING: second.\n"
    )
