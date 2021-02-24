# A simple CLI for BioNetGen 

[![BNG CLI build status](https://github.com/ASinanSaglam/BNG_cli/workflows/bng-cli-tests/badge.svg)](https://github.com/ASinanSaglam/BNG_cli/actions)

## Installation

Use the following pip command

```
$ pip install bionetgen
```

### Features 

PyBioNetGen comes with a command line interface (CLI) entrypoint as well as a functional library that can be imported. The CLI can be used to run BNGL models, generate Jupyter notebooks and do rudimentary plotting. 

The library side provides a simple BNGL model runner as well as a model object that can be manipulated and used to get libRoadRunner simulators for the model. 

The model object requires a system call to BioNetGen so the initialization can be relatively costly, in case you would like to use it for parallel applications, use the libRR simulator for those. 

### Usage 

Sample CLI usage

```
$ bionetgen -h # help on every subcommand
$ bionetgen run -h # help on run subcommand
$ bionetgen run -i mymodel.bngl -o output_folder # this runs the model in output_folder
```

Sample library usage

```
import bionetgen 

ret = bionetgen.run("/path/to/mymodel.bngl", out="/path/to/output/folder")
res = ret.results['mymodel']
# res will be a numpy record array of your gdat results

model = bionetgen.bngmodel("/path/to/mymodel.bngl")
# model will be a python object that contains all model information
print(model.parameters) # this will print only the paramter block in BNGL format
print(model) # this will print the entire BNGL
model.parameters.k = 1 # setting parameter k to 1
with open("new_model.bngl", "w") as f:
    f.write(str(model)) # writes the changed model to new_model file
```

More documentation and tutorials are in progress.

### Environment Setup

The following demonstrates setting up and working with a development environment:

```
### create a virtualenv for development

$ make virtualenv

$ source env/bin/activate


### run bionetgen cli application

$ bionetgen --help


### run pytest / coverage

$ make test
```

### Docker

Included is a basic `Dockerfile` for building and distributing `BioNetGen CLI`,
and can be built with the included `make` helper:

```
$ make docker

$ docker run -it bionetgen --help
```

### Publishing to PyPI

You can use `make dist` command to make the distribution and push to PyPI with

```
python -m twine upload dist/*
```

You'll need to have a PyPI API token created, see [here](https://packaging.python.org/tutorials/packaging-projects/) for more information. 