import os, glob
from pytest import raises
import bionetgen as bng
from bionetgen.main import BioNetGenTest

tfold = os.path.dirname(__file__)

def test_bionetgen_help():
    # test basic command help
    with raises(SystemExit):
        argv = ['--help']
        with BioNetGenTest(argv=argv) as app:
            app.run()
            assert app.exit_code == 0

def test_bionetgen_input(tmp):
    # test basic command help
    argv = ['run','-i', 'test.bngl', '-o', tmp.dir]
    to_match = ['test.xml', 'test.cdat', 'test.gdat', 'test.net']
    with BioNetGenTest(argv=argv) as app:
        app.run()
        assert app.exit_code == 0
        file_list = os.listdir(tmp.dir)
        assert file_list.sort() == to_match.sort()

def test_bionetgen_model(tmp):
    os.chdir(tfold)
    fpath = os.path.abspath("test.bngl")
    m = bng.bngmodel(fpath)

def test_bionetgen_all_model_loading(tmp):
    os.chdir(os.path.join(tfold, "models"))
    models = glob.glob("*.bngl")
    succ = []
    fail = []
    success = 0
    fails = 0 
    models = glob.glob("*.bngl")
    for model in models:
        try:
            m = bng.bngmodel(model)
            success += 1
            succ.append(model)
        except:
            print("can't load model {}".format(model))
            fails += 1
            fail.append(model)
    print("succ: {}".format(success))
    print(sorted(succ))
    print("fail: {}".format(fails))
    print(sorted(fail))
    assert fails == 0