from bionetgen.modelapi.utils import run_command
import cement
import subprocess, os
import bionetgen as bng
from cement.core.exc import CaughtSignal
from .core.exc import BioNetGenError
from .core.main import runCLI
from .core.main import plotDAT
from .core.main import runAtomizeTool
from .core.main import printInfo
from .core.main import visualizeModel
from .core.main import graphDiff
from .core.notebook import BNGNotebook

# pull defaults defined in core/defaults
CONF = bng.defaults
VERSION_BANNER = bng.defaults.banner

# require version argparse action
import argparse, sys
from pkg_resources import packaging


class requireAction(argparse.Action):
    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        if nargs is not None:
            raise ValueError("nargs not allowed")
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)
        if values is not None:
            req_version = packaging.version.parse(values)
            cver = bng.core.version.get_version()
            cur_version = packaging.version.parse(cver)
            # if we don't meet requirement, warn user
            sys.tracebacklimit = 0
            if not (cur_version >= req_version):
                raise RuntimeError(
                    f"Version {values} is required but current version is {cver}. \n"
                    + "Try running `pip install bionetgen --upgrade`"
                )
        # return super().__call__(parser, namespace, values, option_string=option_string)


class BNGBase(cement.Controller):
    """
    Base cement controller for BioNetGen CLI

    Used to set meta attributes like program name (label) as well
    as command line arguments. Each method is a subcommand in the
    command line with its own command line arguments.

    Subcommands
    -------
    run
        runs a model given by -i in folder given by -o
    notebook
        generates and opens a notebook for a model given by -i, optional
    plot
        plots a gdat/cdat/scan file given by -i into file supplied by -o
    info
        provides version and path information about the BNG installation and dependencies
    visualize
        provides various visualization options for BNG models
    """

    class Meta:
        label = "bionetgen"
        description = "A simple CLI to bionetgen <https://bionetgen.org>. Note that you need Perl installed."
        help = "bionetgen"
        arguments = [
            # TODO: Auto-load in BioNetGen version here
            (["-v", "--version"], dict(action="version", version=VERSION_BANNER)),
            # (['-s','--sedml'],dict(type=str,
            #                        default=CONF.config['bionetgen']['bngpath'],
            #                        help="Optional path to SED-ML file, if available the simulation \
            #                              protocol described in SED-ML will be ran")),
            (["-req", "--require"], dict(action=requireAction, type=str, default=None)),
        ]

    # This overwrites the default behavior and runs the CLI object from core/main
    # which in turn just calls BNG2.pl with the supplied options
    @cement.ex(
        help="Runs a given model using BNG2.pl",
        arguments=[
            (
                ["-i", "--input"],
                {
                    "help": "Path to BNGL file (required)",
                    "default": None,
                    "type": str,
                    "required": True,
                },
            ),
            (
                ["-o", "--output"],
                {
                    "help": 'Optional path to output folder (default: ".")',
                    "default": ".",
                    "type": str,
                },
            ),
            (
                ["-l", "--log"],
                {
                    "help": "saves BNG2.pl log to a file given (default: None)",
                    "default": None,
                    "type": str,
                    "dest": "log_file",
                },
            ),
            (
                ["--traceback-depth"],
                {
                    "help": "Sets the traceback depth for python. "
                    + "Defaults to 0 to avoid long tracebacks after a failed BNG2.pl call",
                    "default": 0,
                    "type": int,
                    "dest": "traceback_depth",
                },
            ),
        ],
    )
    def run(self):
        """
        This is the main run functionality of the CLI.

        It uses a convenience function defined in core/main
        to run BNG2.pl using subprocess, given the set of arguments
        in the command line and the configuraions set by the defaults
        as well as the end-user.
        """
        args = self.app.pargs
        runCLI(self.app.config, args)

    @cement.ex(
        help="Starts a Jupyter notebook to help run and analyze \
                  bionetgen models",
        arguments=[
            (
                ["-i", "--input"],
                {
                    "help": "Path to BNGL file to use with notebook",
                    "default": None,
                    "type": str,
                    "required": False,
                },
            ),
            (
                ["-o", "--output"],
                {
                    "help": "(optional) File to write the notebook in",
                    "default": "",
                    "type": str,
                },
            ),
            (
                ["-op", "--open"],
                {
                    "help": "(optional) If given, the notebook will by opened using nbopen",
                    "action": "store_true",
                },
            ),
        ],
    )
    def notebook(self):
        """
        Notebook subcommand that boots up a Jupyter notebook using the
        nbopen library. It uses a BNGNotebook class defined in core/notebook.

        The default template can be found under assets and in the future
        will likely be replaced by a standard templating tool (e.g. Jinja).

        The default base template is agnostic to the model and if -i is given
        the template then will be adjusted to load in the model supplied.
        """
        args = self.app.pargs
        if args.input is not None:
            # we want to use the template to write a custom notebok
            assert args.input.endswith(
                ".bngl"
            ), f"File {args.input} doesn't have bngl extension!"
            try:
                import bionetgen

                m = bionetgen.bngmodel(args.input)
                str(m)
            except:
                raise RuntimeError(f"Couldn't import given model: {args.input}!")
            notebook = BNGNotebook(
                self.app.config["bionetgen"]["notebook"]["template"],
                INPUT_ARG=args.input,
            )
        else:
            # just use the basic notebook
            notebook = BNGNotebook(self.app.config["bionetgen"]["notebook"]["path"])
        # find our file name
        if len(args.output) == 0:
            fname = self.app.config["bionetgen"]["notebook"]["name"]
        else:
            fname = args.output
        # write the notebook out
        if os.path.isdir(fname):
            if args.input is not None:
                basename = os.path.basename(args.input)
                mname = basename.replace(".bngl", "")
                fname = mname + ".ipynb"
            else:
                mname = self.app.config["bionetgen"]["notebook"]["name"]
                fname = os.path.join(args.output, mname)

        notebook.write(fname)
        # open the notebook with nbopen
        stdout = getattr(subprocess, self.app.config["bionetgen"]["stdout"])
        stderr = getattr(subprocess, self.app.config["bionetgen"]["stderr"])
        if args.open:
            command = ["nbopen", fname]
            rc, _ = run_command(command)

    @cement.ex(
        help="Rudimentary plotting of gdat/cdat/scan files",
        arguments=[
            (
                ["-i", "--input"],
                {
                    "help": "Path to .gdat/.cdat file to use plot",
                    "default": None,
                    "type": str,
                    "required": True,
                },
            ),
            (
                ["-o", "--output"],
                {
                    "help": 'Optional path for the plot (default: "$model_name.png")',
                    "default": ".",
                    "type": str,
                },
            ),
            (
                ["--legend"],
                {
                    "help": "To plot the legend or not (default: False)",
                    "default": False,
                    "action": "store_true",
                    "required": False,
                },
            ),
            (
                ["--xmin"],
                {
                    "help": "x-axis minimum (default: determined from data)",
                    "default": None,
                    "type": float,
                },
            ),
            (
                ["--xmax"],
                {
                    "help": "x-axis maximum (default: determined from data)",
                    "default": False,
                    "type": float,
                },
            ),
            (
                ["--ymin"],
                {
                    "help": "y-axis minimum (default: determined from data)",
                    "default": False,
                    "type": float,
                },
            ),
            (
                ["--ymax"],
                {
                    "help": "y-axis maximum (default: determined from data)",
                    "default": False,
                    "type": float,
                },
            ),
            (["--xlabel"], {"help": "x-axis label (default: time)", "default": False}),
            (
                ["--ylabel"],
                {"help": "y-axis label (default: concentration)", "default": False},
            ),
            (
                ["--title"],
                {
                    "help": "title of plot (default: determined from input file)",
                    "default": False,
                },
            ),
        ],
    )
    def plot(self):
        """
        Plotting subcommand for very basic plotting using a convenience function
        defined in core/main.

        Currently we support gdat/cdat/scan file plotting, in a very basic manner.
        This command expects a space separated file where each column is a series.
        The first column is used for the x-axis and the rest is used as y-axis
        and every series is plotted.

        See bionetgen plot -h for all the allowed options.
        """
        args = self.app.pargs
        # we need to have gdat/cdat files
        assert (
            args.input.endswith(".gdat")
            or args.input.endswith(".cdat")
            or args.input.endswith(".scan")
        ), "Input file has to be either a gdat or a cdat file"
        plotDAT(args.input, args.output, kw=dict(args._get_kwargs()))

    @cement.ex(
        help="Provides version information for BNG and dependencies",
        arguments=[
            (
                ["-d", "--detail"],
                {
                    "help": "Adds more detail to the information printed.",
                    "default": False,
                    "action": "store_true",
                },
            ),
        ],
    )
    def info(self):
        """
        Information subcommand to provide installation versions and paths.

        Currently provides version information for BioNetGen, the BNG CLI, Perl,
        numpy, pandas, and libroadrunner. Also provides BNG2.pl and pyBNG paths.
        """
        args = self.app.pargs
        printInfo(self.app.config, args)

    @cement.ex(
        help="Provides a simple way to get various visualizations of the model.",
        arguments=[
            (
                ["-i", "--input"],
                {
                    "help": "Path to BNGL model to visualize",
                    "default": None,
                    "type": str,
                    "required": True,
                },
            ),
            (
                ["-o", "--output"],
                {
                    "help": "(optional) Output folder, defaults to current folder",
                    "default": None,
                    "type": str,
                },
            ),
            (
                ["-t", "--type"],
                {
                    "help": "(optional) Type of visualization requested. Valid options are: "
                    + "'ruleviz_pattern','ruleviz_operation', 'contactmap' and 'regulatory'."
                    + " Defaults to 'contactmap'.",
                    "default": "",
                    "type": str,
                },
            ),
        ],
    )
    def visualize(self):
        """
        Subcommand to generate visualizations. Currently only supports visualize
        action from BioNetGen.

        Types of visualizations and their options
        - Rule pattern visualization: Visualization of each rule as a bipartite graph
        - Rule operation visualization: Visualization of each rule showing explicit graph operations
        - Contact map: Visualize the contact map of the model
        - Regulatory graph: Visualize the regulatory graph of the model
        """
        args = self.app.pargs
        visualizeModel(self.app.config, args)

    @cement.ex(
        help="A subcommand to compare two contact maps made by BioNetGen. "
        + 'The default mode is "matrix" mode and will generate 4 graphs, two for each individual input '
        + "recolored, one for input 1 - input 2 and one for input 2 - input 1. This can be used to find "
        + "differences and communalities between two BNGL models of the same process. ",
        arguments=[
            (
                ["-i", "--input"],
                {
                    "help": "Path to the first graphml file to diff",
                    "default": None,
                    "type": str,
                    "required": True,
                },
            ),
            (
                ["-i2", "--input2"],
                {
                    "help": "Path to the second graphml file to diff",
                    "default": None,
                    "type": str,
                    "required": True,
                },
            ),
            (
                ["-o", "--output"],
                {
                    "help": "(optional) Output graphml file for the diff input 1 - input 2",
                    "default": None,
                    "type": str,
                    "required": False,
                },
            ),
            (
                ["-o2", "--output2"],
                {
                    "help": "(optional) Output graphml file for the diff input 2 - input 1",
                    "default": None,
                    "type": str,
                    "required": False,
                },
            ),
            (
                ["-m", "--mode"],
                {
                    "help": 'Diff mode. There are currently two available modes "matrix" and "union".',
                    "default": "matrix",
                    "type": str,
                },
            ),
            (
                ["-c", "--colors"],
                {
                    "help": "Path to the json file that contains color choices.",
                    "default": None,
                    "type": str,
                },
            ),
        ],
    )
    def graphdiff(self):
        """ """
        args = self.app.pargs
        graphDiff(self.app.config, args)

    @cement.ex(
        help="SBML to BNGL translator",
        arguments=[
            (
                ["-i", "--input"],
                {
                    "help": "input SBML file",
                    "default": None,
                    "type": str,
                    "required": True,
                },
            ),
            (
                ["-o", "--output"],
                {
                    "help": "output SBML file",
                    "default": ".",
                    "type": str,
                },
            ),
            (
                ["-t", "--annotation"],
                {
                    "help": "keep annotation information",
                    "default": False,
                    "action": "store_true",
                },
            ),
            (
                ["-c", "--convention-file"],
                {
                    "help": "Conventions file",
                    "type": str,
                },
            ),
            (
                ["-n", "--naming-conventions"],
                {
                    "help": "Naming conventions file",
                    "type": str,
                },
            ),
            (
                ["-u", "--user-structures"],
                {
                    "help": "User defined species",
                    "type": str,
                },
            ),
            (
                ["-id", "--molecule-id"],
                {
                    "help": "use SBML molecule ids instead of names. IDs are less descriptive but more bngl friendly. Use only if the generated BNGL has syntactic errors",
                    "default": False,
                    "action": "store_true",
                },
            ),
            (
                ["-a", "--atomize"],
                {
                    "help": "Infer molecular structure",
                    "default": False,
                    "action": "store_true",
                },
            ),
            (
                ["-p", "--pathwaycommons"],
                {
                    "help": "Don't use web services to infer information on the SBML species. Use this setting when you don't have an internet connection.",
                    "default": True,
                    "action": "store_false",
                },
            ),
            (
                ["-s", "--isomorphism-check"],
                {
                    "help": "disallow atomizations that produce the same graph structure",
                    "action": "store_true",
                },
            ),
            (
                ["-I", "--ignore"],
                {
                    "help": "ignore atomization translation errors",
                    "action": "store_true",
                },
            ),
            (
                ["-mr", "--memoized-resolver"],
                {
                    "help": "sometimes the dependency graph is too large and might cause a very large memory requirement. This option will slow the translator down but will decrease memory usage",
                    "default": False,
                    "action": "store_true",
                },
            ),
            (
                ["-k", "--keep-local-parameters"],
                {
                    "help": "this option will keep the local parameters unresolved so that they can be controlled from the parameter section in the BNGL. Without this option, local parameters will be resolved to their values in functions",
                    "default": False,
                    "action": "store_true",
                },
            ),
            (
                ["-q", "--quiet-mode"],
                {
                    "help": "this option will supress logging into STDIO and instead will write the logging into a file",
                    "default": False,
                    "action": "store_true",
                },
            ),
            (
                ["-ll", "--log-level"],
                {
                    "help": 'This option allows you to select a logging level, from quietest to loudest options are: "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG". Default is set to WARNING',
                    "default": "WARNING",
                    "type": str,
                },
            ),
            (
                ["-omf", "--obs-map-file"],
                {
                    "help": "With this option enabled atomizer will print the map between SBML and BNGL observables in JSON format",
                    "default": None,
                    "type": str,
                },
            ),
            # (
            #     ["-cu", "--convert-units"],
            #     {
            #         "help": "convert units. Otherwise units are copied straight from sbml to bngl",
            #         "default": True,
            #         "action": "store_false",
            #     },
            # ),
        ],
    )
    def atomize(self):
        args = self.app.pargs
        runAtomizeTool(self.app.config, args)


class BioNetGen(cement.App):
    """
    Cement app for BioNetGen CLI

    Used to set configuration options like config default,
    exiting on close and setting log handler. Currently set
    attributes are below.

    Attributes
    ----------
    label : str
        name of the application
    config_defaults : str
        the default set of configuration options, set in BNGDefaults object
    config_handler: str
        the name of the config handler, determines the syntax of the config files
    config_file_suffix: str
        the suffix to be used for config files
    config_files: list of str
        additional list of config files to enable
    exit_on_close : boolean
        determine if the app should exit when the key function is ran
    extensions : list of str
        extensions to be used with cement framework
    log_handler: str
        name of the log handler
    handlers: list of obj
        list of objects derived from cement.Controller that handles the actual CLI
    """

    class Meta:
        label = "bionetgen"

        # configuration defaults
        config_defaults = CONF.config

        # call sys.exit() on close
        exit_on_close = True

        # load additional framework extensions
        extensions = [
            "colorlog",
        ]

        # configuration handler
        config_handler = "configparser"

        # configuration file suffix
        config_file_suffix = ".conf"

        # add current folder to the list of config dirs
        config_files = ["./.{}.conf".format(label)]

        # set the log handler
        log_handler = "colorlog"

        # register handlers
        handlers = [BNGBase]


class BioNetGenTest(cement.TestApp, BioNetGen):
    """
    A sub-class of BioNetGen CLI application for testing
    purposes. See tests/test_bionetgen.py for examples.
    """

    class Meta:
        label = "bionetgen"


def main():
    with BioNetGen() as app:
        try:
            app.run()

        except AssertionError as e:
            print("AssertionError > %s" % e.args[0])
            app.exit_code = 1

            if app.debug is True:
                import traceback

                traceback.print_exc()

        except BioNetGenError as e:
            print("BioNetGenError > %s" % e.args[0])
            app.exit_code = 1

            if app.debug is True:
                import traceback

                traceback.print_exc()

        except CaughtSignal as e:
            # Default Cement signals are SIGINT and SIGTERM, exit 0 (non-error)
            print("\n%s" % e)
            app.exit_code = 0


if __name__ == "__main__":
    main()
