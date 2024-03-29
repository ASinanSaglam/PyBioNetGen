import os
from re import sub
import subprocess
from distutils import spawn


class ActionList:
    def __init__(self):
        # these are all the action types, categorized
        # by their argument syntax
        self.normal_types = [
            "generate_network",
            "generate_hybrid_model",
            "simulate",
            "simulate_ode",
            "simulate_ssa",
            "simulate_pla",
            "simulate_nf",
            "parameter_scan",
            "bifurcate",
            "readFile",
            "writeFile",
            "writeModel",
            "writeNetwork",
            "writeXML",
            "writeSBML",
            "writeMfile",
            "writeMexfile",
            "writeMDL",
            "visualize",
        ]
        self.no_setter_syntax = [
            "setConcentration",
            "addConcentration",
            "setParameter",
            "quit",
            "setModelName",
            "substanceUnits",
            "version",
            "setOption",
        ]
        self.square_braces = [
            "saveConcentrations",
            "resetConcentrations",
            "resetParameters",
            "saveParameters",
        ]
        # remember what's written before models
        self.before_model = [
            "setModelName",
            "substanceUnits",
            "version",
            "setOption",
        ]
        self.possible_types = (
            self.normal_types + self.no_setter_syntax + self.square_braces
        )
        # Use dictionary to keep track of all possible args (and types?) for each action
        self.arg_dict = {}
        # arg_dict["action"] = ["arg1", "arg2", "etc."]
        # normal_types
        self.arg_dict["generate_network"] = [
            "prefix",
            "suffix",
            "verbose",
            "overwrite",
            "print_iter",
            "max_agg",
            "max_iter",
            "max_stoich",
            "TextReaction",
            "TextSpecies",
        ]
        self.arg_dict["generate_hybrid_model"] = [
            "prefix",
            "suffix",
            "verbose",
            "overwrite",
            "actions",
            "execute",
            "safe",
        ]
        self.arg_dict["simulate"] = [
            "prefix",
            "suffix",
            "verbose",
            "method",
            "argfile",
            "continue",
            "t_start",
            "t_end",
            "n_steps",
            "n_output_steps",
            "sample_times",
            "output_step_interval",
            "max_sim_steps",
            "stop_if",
            "print_on_stop",
            "print_end",
            "print_net",
            "save_progress",
            "print_CDAT",
            "print_functions",
            "netfile",
            "seed",
            # TODO: arguments for a method called "psa" that is not documented in
            # https://docs.google.com/spreadsheets/d/1Co0bPgMmOyAFxbYnGCmwKzoEsY2aUCMtJXQNpQCEUag/
            "poplevel",
            "check_product_scale",
        ]
        self.arg_dict["simulate_ode"] = [
            "prefix",
            "suffix",
            "verbose",
            "argfile",
            "continue",
            "t_start",
            "t_end",
            "n_steps",
            "n_output_steps",
            "sample_times",
            "output_step_interval",
            "max_sim_steps",
            "stop_if",
            "print_on_stop",
            "print_end",
            "print_net",
            "save_progress",
            "print_CDAT",
            "print_functions",
            "netfile",
            "seed",
            "atol",
            "rtol",
            "sparse",
            "steady_state",
        ]
        self.arg_dict["simulate_ssa"] = [
            "prefix",
            "suffix",
            "verbose",
            "argfile",
            "continue",
            "t_start",
            "t_end",
            "n_steps",
            "n_output_steps",
            "sample_times",
            "output_step_interval",
            "max_sim_steps",
            "stop_if",
            "print_on_stop",
            "print_end",
            "print_net",
            "save_progress",
            "print_CDAT",
            "print_functions",
            "netfile",
            "seed",
        ]
        self.arg_dict["simulate_pla"] = [
            "prefix",
            "suffix",
            "verbose",
            "argfile",
            "continue",
            "t_start",
            "t_end",
            "n_steps",
            "n_output_steps",
            "sample_times",
            "output_step_interval",
            "max_sim_steps",
            "stop_if",
            "print_on_stop",
            "print_end",
            "print_net",
            "save_progress",
            "print_CDAT",
            "print_functions",
            "netfile",
            "seed",
            "pla_config",
            "pla_output",
        ]
        self.arg_dict["simulate_nf"] = [
            "prefix",
            "suffix",
            "verbose",
            "argfile",
            "continue",
            "t_start",
            "t_end",
            "n_steps",
            "n_output_steps",
            "sample_times",
            "output_step_interval",
            "max_sim_steps",
            "stop_if",
            "print_on_stop",
            "print_end",
            "print_net",
            "save_progress",
            "print_CDAT",
            "print_functions",
            "netfile",
            "seed",
            "complex",
            "nocslf",
            "notf",
            "binary_output",
            "gml",
            "equil",
            "get_final_state",
            "utl",
            "param",
        ]
        self.arg_dict["simulate"] = list(
            set(
                self.arg_dict["simulate"]
                + self.arg_dict["simulate_ode"]
                + self.arg_dict["simulate_ssa"]
                + self.arg_dict["simulate_pla"]
                + self.arg_dict["simulate_nf"]
            )
        )
        self.arg_dict["parameter_scan"] = [
            "prefix",
            "suffix",
            "verbose",
            "method",
            "argfile",
            "continue",
            "t_start",
            "t_end",
            "n_steps",
            "n_output_steps",
            "sample_times",
            "output_step_interval",
            "max_sim_steps",
            "stop_if",
            "print_on_stop",
            "print_end",
            "print_net",
            "save_progress",
            "print_CDAT",
            "print_functions",
            "netfile",
            "seed",
            "parameter",
            "par_min",
            "par_max",
            "n_scan_pts",
            "log_scale",
            "par_scan_vals",
            "reset_conc",
        ]
        self.arg_dict["parameter_scan"] = list(
            set(self.arg_dict["parameter_scan"] + self.arg_dict["simulate"])
        )
        self.arg_dict["bifurcate"] = [
            "prefix",
            "suffix",
            "verbose",
            "method",
            "argfile",
            "continue",
            "t_start",
            "t_end",
            "n_steps",
            "n_output_steps",
            "sample_times",
            "output_step_interval",
            "max_sim_steps",
            "stop_if",
            "print_on_stop",
            "print_end",
            "print_net",
            "save_progress",
            "print_CDAT",
            "print_functions",
            "netfile",
            "seed",
            "parameter",
            "par_min",
            "par_max",
            "n_scan_pts",
            "log_scale",
            "par_scan_vals",
        ]
        self.arg_dict["bifurcate"] = list(
            set(self.arg_dict["bifurcate"] + self.arg_dict["parameter_scan"])
        )
        self.arg_dict["bifurcate"].remove("reset_conc")
        self.arg_dict["readFile"] = ["file", "blocks", "atomize", "skip_actions"]
        self.arg_dict["writeFile"] = [
            "format",
            "prefix",
            "suffix",
            "evaluate_expressions",
            "include_model",
            "include_network",
            "overwrite",
            "pretty_formatting",
            "TextReaction",
            "TextSpecies",
        ]
        self.arg_dict["writeModel"] = [
            "format",
            "prefix",
            "suffix",
            "evaluate_expressions",
            "include_model",
            "include_network",
            "overwrite",
            "pretty_formatting",
            "TextReaction",
            "TextSpecies",
        ]
        self.arg_dict["writeNetwork"] = [
            "format",
            "prefix",
            "suffix",
            "evaluate_expressions",
            "include_model",
            "include_network",
            "overwrite",
            "pretty_formatting",
            "TextReaction",
            "TextSpecies",
        ]
        self.arg_dict["writeXML"] = [
            "format",
            "prefix",
            "suffix",
            "evaluate_expressions",
            "include_model",
            "include_network",
            "overwrite",
            "pretty_formatting",
            "TextReaction",
            "TextSpecies",
        ]
        self.arg_dict["writeSBML"] = ["prefix", "suffix"]
        self.arg_dict["writeMfile"] = [
            "prefix",
            "suffix",
            "t_start",
            "t_end",
            "n_steps",
            "atol",
            "rtol",
            "max_step",
            "bdf",
            "maxOrder",
            "stats",
        ]
        self.arg_dict["writeMexfile"] = [
            "prefix",
            "suffix",
            "t_start",
            "t_end",
            "n_steps",
            "atol",
            "rtol",
            "max_step",
            "max_num_steps",
            "max_err_test_fails",
            "max_conv_fails",
            "stiff",
            "sparse",
        ]
        self.arg_dict["writeMDL"] = ["prefix", "suffix"]
        self.arg_dict["visualize"] = [
            "type",
            "help",
            "suffix",
            "each",
            "background",
            "groups",
            "collapse",
            "filter",
            "level",
            "textonly",
            "opts",
        ]
        # no_setter_syntax
        self.arg_dict["setConcentration"] = []
        self.arg_dict["addConcentration"] = []
        self.arg_dict["setParameter"] = []
        self.arg_dict["saveParameters"] = []
        self.arg_dict["quit"] = None
        self.arg_dict["setModelName"] = []
        self.arg_dict["substanceUnits"] = []
        self.arg_dict["version"] = []
        self.arg_dict["setOption"] = []
        # square_braces
        self.arg_dict["saveConcentrations"] = []
        self.arg_dict["resetConcentrations"] = []
        self.arg_dict["resetParameters"] = []

        # irregular arg types
        self.irregular_args = {}
        self.irregular_args["max_stoich"] = "dict"
        self.irregular_args["actions"] = "list"
        self.irregular_args["sample_times"] = "list"
        self.irregular_args["par_scan_vals"] = "list"
        self.irregular_args["blocks"] = "list"
        self.irregular_args["opts"] = "list"

    def is_before_model(self, action_name):
        if action_name in self.before_model:
            return True
        return False

    def define_parser(self):
        ## Define action grammar
        import pyparsing as pp

        #
        base_name = pp.Word(pp.alphas, pp.alphanums + "_")
        action_name = base_name
        #
        dquote_word = pp.dblQuotedString
        squote_word = pp.sglQuotedString
        quote_word = dquote_word ^ squote_word
        # all action argument types
        # TODO: deal w/ zero argument list
        list_arg = "[" + pp.delimitedList(quote_word) + "]"
        #
        arg_type_bool = pp.Word("0") ^ pp.Word("1")
        arg_type_int = pp.Word(pp.nums)
        arg_type_float = pp.Word(pp.nums + ".")
        arg_type_expr = pp.Word(
            pp.nums + "." + "+" + "-" + "e" + "E" + "(" + ")" + "/" + "*" + "^"
        )
        arg_type_list = "[" + pp.delimitedList((quote_word ^ arg_type_float)) + "]"
        arg_type_string = quote_word
        #
        curly_arg_token = quote_word + "=>" + arg_type_int
        # TODO: handle 0 case
        arg_type_curly = "{" + pp.delimitedList(curly_arg_token) + "}"
        arg_types = (
            arg_type_bool
            ^ arg_type_int
            ^ arg_type_float
            ^ arg_type_list
            ^ arg_type_list
            ^ arg_type_string
            ^ arg_type_curly
            ^ arg_type_expr
        )
        #
        one_arg = quote_word
        two_arg = quote_word + "," + (arg_type_expr ^ quote_word)
        #
        single_arg = base_name + "=>" + arg_types
        #
        reg_arg_full = "{" + pp.Optional(pp.delimitedList(single_arg)) + "}"
        #
        reg_action_tk = (
            action_name + "(" + reg_arg_full + ")" + pp.Optional(";") + pp.stringEnd
        )
        two_arg_action_tk = (
            action_name
            + "("
            + quote_word
            + ","
            + pp.SkipTo(")" + pp.Optional(";") + pp.stringEnd)
            + ")"
            + pp.Optional(";")
            + pp.stringEnd
        )
        one_arg_action_tk = (
            action_name
            + "("
            + pp.Optional(one_arg)
            + ")"
            + pp.Optional(";")
            + pp.stringEnd
        )
        list_arg_action_tk = (
            action_name + "(" + list_arg + ")" + pp.Optional(";") + pp.stringEnd
        )
        full_action_tk = (
            reg_action_tk ^ list_arg_action_tk ^ two_arg_action_tk ^ one_arg_action_tk
        )
        ## Action grammar done
        self.action_parser = full_action_tk


def find_BNG_path(BNGPATH=None):
    """
    A simple function finds the path to BNG2.pl from
    * Environment variable
    * Assuming it's under PATH
    * Given optional path as argument

    Usage: test_bngexec(path)
           test_bngexec()

    Arguments
    ---------
    BNGPATH : str
        (optional) path to the folder that contains BNG2.pl
    """
    # TODO: Figure out how to use the BNG2.pl if it's set
    # in the PATH variable. Solution: set os.environ BNGPATH
    # and make everything use that route

    # Let's keep up the idea we pull this path from the environment
    if BNGPATH is None:
        try:
            BNGPATH = os.environ["BNGPATH"]
        except:
            pass
    # if still none, try pulling it from cmd line
    if BNGPATH is None:
        bngexec = "BNG2.pl"
        if test_bngexec(bngexec):
            # print("BNG2.pl seems to be working")
            # get the source of BNG2.pl
            BNGPATH = spawn.find_executable("BNG2.pl")
            BNGPATH, _ = os.path.split(BNGPATH)
    else:
        bngexec = os.path.join(BNGPATH, "BNG2.pl")
        if not test_bngexec(bngexec):
            RuntimeError("BNG2.pl is not working")
    return BNGPATH, bngexec


def test_bngexec(bngexec):
    """
    A simple function that test if BNG2.pl given runs

    Usage: test_bngexec(path)

    Arguments
    ---------
    bngexec : str
        path to BNG2.pl to test
    """
    command = ["perl", bngexec]
    rc, _ = run_command(command, suppress=True)
    if rc == 0:
        return True
    else:
        return False


def run_command(command, suppress=False, timeout=None):
    if timeout is not None:
        # I am unsure how to do both timeout and the live polling of stdo
        rc = subprocess.run(command, timeout=timeout, capture_output=True)
        return rc.returncode, rc
    else:
        if suppress:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                bufsize=-1,
            )
            return process.poll(), process
        else:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, encoding="utf8")
            out = []
            while True:
                output = process.stdout.readline()
                if output == "" and process.poll() is not None:
                    break
                if output:
                    o = output.strip()
                    out.append(o)
                    print(o)
            rc = process.poll()
            return rc, out
