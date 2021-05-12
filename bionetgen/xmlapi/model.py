import bionetgen as bng
import subprocess, os, xmltodict, sys

from bionetgen.main import BioNetGen
from tempfile import TemporaryDirectory
from tempfile import TemporaryFile
from .utils import find_BNG_path
from .bngparser import BNGParser
from .structs import Parameters, Species, MoleculeTypes, Observables, Functions, Compartments, Rules, Actions


# This allows access to the CLIs config setup
app = BioNetGen()
app.setup()
conf = app.config['bionetgen']
def_bng_path = conf['bngpath']

###### CORE OBJECT AND PARSING FRONT-END ######
class bngmodel:
    '''
    Main model object and entry point for XMLAPI. The goal of this 
    object is to generate and read the BNGXML of a given BNGL model
    and give the user a pythonic interface to the resulting model object. 

    Usage: bngmodel(bng_model)
           bngmodel(bng_model, BNGPATH)

    Attributes
    ----------
    active_blocks : list[str]
        a list of the blocks that have been parsed in the model
    bngparser : BNGParser
        BNGParser object that's responsible for .bngl file reading and model setup
    BNGPATH : str
        path to bionetgen where BNG2.pl lives
    bngexec : str
        path to BNG2.pl
    model_name : str
        name of the model, generally set from the given BNGL file
    recompile : bool
        a tag to keep track if any changes have been made to the model
        via the XML API by the user
    changes : dict
        a list of changes the user have made to the model
    
    Methods
    -------
    reset_compilation_tags()
        resets compilation tags of each block to keep track of any changes the user
        makes to the model via the API
    add_action(action_type, action_args)
        adds the action of action_type with arguments given by the optional keyword
        argument action_args which is a list of lists where each element 
        is of the form [ArgumentName, ArgumentValue]
    write_model(model_name)
        write the model in BNGL format to the path given
    write_xml(open_file, xml_type)
        writes the XML of the model into the open_file object given. xml_types allowed
        are BNGXML or SBML formats.
    setup_simulator(sim_type)
        sets up a simulator in bngmodel.simulator where the only current supported 
        type of simulator is libRR for libRoadRunner simulator.
    '''
    def __init__(self, bngl_model, BNGPATH=def_bng_path):
        self.active_blocks = []
        # We want blocks to be printed in the same order every time
        self.block_order = ["parameters", "compartments", "moltypes", 
                            "species", "observables", "functions", 
                            "rules", "actions"]
        BNGPATH, bngexec = find_BNG_path(BNGPATH)
        self.BNGPATH = BNGPATH
        self.bngexec = bngexec 
        self.model_name = ""
        self.bngparser = BNGParser(bngl_model)
        self.bngparser.parse_model(self)

    @property
    def recompile(self):
        recompile = False
        for block in self.active_blocks:
            recompile = recompile or getattr(self, block)._recompile
        return recompile

    @property
    def changes(self):
        changes = {}
        for block in self.active_blocks:
            changes[block] = getattr(self, block)._changes
        return changes 

    def __str__(self):
        '''
        write the model to str
        '''
        model_str = "begin model\n"
        for block in self.block_order:
            if block in self.active_blocks:
                if block != "actions":
                    model_str += str(getattr(self, block))
        model_str += "\nend model\n"
        if "actions" in self.active_blocks:
            model_str += str(self.actions)
        return model_str

    def __repr__(self):
        return self.model_name

    def __iter__(self):
        active_ordered_blocks = [getattr(self,i) for i in self.block_order if i in self.active_blocks]
        return active_ordered_blocks.__iter__()

    def reset_compilation_tags(self):
        for block in self.active_blocks:
            getattr(self, block).reset_compilation_tags()

    def add_action(self, action_type, action_args=[]):
        # add actions block and to active list
        if not hasattr(self, "actions"):
            self.actions = Actions()
            self.active_blocks.append("actions")
        self.actions.add_action(action_type, action_args)

    def write_model(self, file_name):
        '''
        write the model to file 
        '''
        model_str = ""
        for block in self.active_blocks:
            model_str += str(getattr(self, block))
        with open(file_name, 'w') as f:
            f.write(model_str)

    def write_xml(self, open_file, xml_type="bngxml"):
        '''
        write new XML to file by calling BNG2.pl again
        '''
        cur_dir = os.getcwd()
        # temporary folder to work in
        with TemporaryDirectory() as temp_folder:
            # write the current model to temp folder
            os.chdir(temp_folder)
            with open("temp.bngl", "w") as f:
                f.write(str(self))
            # run with --xml 
            # TODO: Make output supression an option somewhere
            if xml_type == "bngxml":
                rc = subprocess.run(["perl",self.bngexec, "--xml", "temp.bngl"], stdout=bng.defaults.stdout)
                if rc.returncode == 1:
                    print("XML generation failed")
                    # go back to our original location
                    os.chdir(cur_dir)
                    return False
                else:
                    # we should now have the XML file 
                    with open("temp.xml", "r") as f:
                        content = f.read()
                        open_file.write(content)
                    # go back to beginning
                    open_file.seek(0)
                    os.chdir(cur_dir)
                    return True
            elif xml_type == "sbml":
                rc = subprocess.run(["perl",self.bngexec, "temp.bngl"], stdout=bng.defaults.stdout)
                if rc.returncode == 1:
                    print("SBML generation failed")
                    # go back to our original location
                    os.chdir(cur_dir)
                    return False
                else:
                    # we should now have the SBML file 
                    with open("temp_sbml.xml", "r") as f:
                        content = f.read()
                        open_file.write(content)
                    open_file.seek(0)
                    os.chdir(cur_dir)
                    return True
            else: 
                print("XML type {} not recognized".format(xml_type))
            return False

    def setup_simulator(self, sim_type="libRR"):
        '''
        Sets up a simulator attribute that is a generic front-end
        to all other simulators. At the moment only libroadrunner
        is supported
        '''
        if sim_type == "libRR":
            # we need to add writeSBML action for now
            self.add_action("generate_network", [("overwrite",1)])
            self.add_action("writeSBML", [])
            # temporary file
            with TemporaryFile(mode="w+") as tpath:
                # write the sbml
                self.write_xml(tpath, xml_type="sbml")
                # TODO: Only clear the writeSBML action
                # by adding a mechanism to do so
                self.actions.clear_actions()
                # get the simulator
                self.simulator = bng.sim_getter(model_str=tpath.read(), sim_type=sim_type)
        else:
            print("Sim type {} is not recognized, only libroadrunner \
                   is supported currently by passing libRR to \
                   sim_type keyword argument".format(sim_type))
        return self.simulator

###### CORE OBJECT AND PARSING FRONT-END ######