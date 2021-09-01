# -*- coding: utf-8 -*-
"""
Created on Fri Nov 14 18:17:20 2014

@author: proto
"""

import libsbml
from util import logMess
from sbml2bngl import SBML2BNGL as SBML2BNGL
import structures
import atomizer.resolveSCT as mc
import os
from subprocess import call
import tempfile
import sys

# sys.path.insert(0, '../utils/')
import consoleCommands
import readBNGXML
import argparse

bioqual = [
    "BQB_IS",
    "BQB_HAS_PART",
    "BQB_IS_PART_OF",
    "BQB_IS_VERSION_OF",
    "BQB_HAS_VERSION",
    "BQB_IS_HOMOLOG_TO",
    "BQB_IS_DESCRIBED_BY",
    "BQB_IS_ENCODED_BY",
    "BQB_ENCODES",
    "BQB_OCCURS_IN",
    "BQB_HAS_PROPERTY",
    "BQB_IS_PROPERTY_OF",
    "BQB_HAS_TAXON",
    "BQB_UNKNOWN",
]

modqual = [
    "BQM_IS",
    "BQM_IS_DESCRIBED_BY",
    "BQM_IS_DERIVED_FROM",
    "BQM_IS_INSTANCE_OF",
    "BQM_HAS_INSTANCE",
    "BQM_UNKNOWN",
]


import fnmatch
import argparse


def getFiles(directory, extension):
    """
    Gets a list of <*.extension> files. include subdirectories and return the absolute
    path. also sorts by size.
    """
    matches = []
    for root, dirnames, filenames in os.walk(directory):
        for filename in fnmatch.filter(filenames, "*.{0}".format(extension)):
            matches.append(
                [
                    os.path.join(os.path.abspath(root), filename),
                    os.path.getsize(os.path.join(root, filename)),
                ]
            )

    # sort by size
    matches.sort(key=lambda filename: filename[1], reverse=False)

    matches = [x[0] for x in matches]

    return matches


from collections import defaultdict
import re


def standardizeName(name):
    """
    Remove stuff not used by bngl
    """
    name2 = name

    sbml2BnglTranslationDict = {
        "^": "",
        "'": "",
        "*": "m",
        " ": "_",
        "#": "sh",
        ":": "_",
        "α": "a",
        "β": "b",
        "γ": "g",
        " ": "",
        "+": "pl",
        "/": "_",
        ":": "_",
        "-": "_",
        ".": "_",
        "?": "unkn",
        ",": "_",
        "(": "",
        ")": "",
        "[": "",
        "]": "",
        # "(": "__",
        # ")": "__",
        # "[": "__",
        # "]": "__",
        "(": "",
        ")": "",
        "[": "",
        "]": "",
        ">": "_",
        "<": "_",
    }

    for element in sbml2BnglTranslationDict:
        name = name.replace(element, sbml2BnglTranslationDict[element])
    name = re.sub("[\W]", "", name)
    return name


def parseAnnotation(annotation):
    speciesAnnotationDict = defaultdict(list)
    lista = libsbml.CVTermList()
    libsbml.RDFAnnotationParser.parseRDFAnnotation(annotation, lista)
    for idx in range(0, lista.getSize()):
        for idx2 in range(0, lista.get(idx).getResources().getLength()):
            resource = lista.get(idx).getResources().getValue(idx2)

            qualifierType = lista.get(idx).getQualifierType()
            qualifierDescription = (
                bioqual[lista.get(idx).getBiologicalQualifierType()]
                if qualifierType
                else modqual[lista.get(idx).getModelQualifierType()]
            )
            speciesAnnotationDict[qualifierDescription].append(resource)
    return speciesAnnotationDict


def buildAnnotationDict(document):
    annotationDict = defaultdict(lambda: defaultdict(list))
    speciesNameDict = {}
    for species in document.getModel().getListOfSpecies():
        annotation = species.getAnnotation()
        transformedName = standardizeName(species.getName())
        speciesNameDict[transformedName] = species.getName()
        speciesNameDict[species.getName()] = transformedName
        if annotation:
            annotationDict[transformedName] = parseAnnotation(annotation)
    return annotationDict, speciesNameDict


def updateFromParent(child, parent, annotationDict):
    for annotationLabel in annotationDict[parent]:
        if annotationLabel in [
            "BQB_IS_VERSION_OF",
            "BQB_IS",
            "BQB_IS_HOMOLOG_TO",
            "BQB_HAS_VERSION",
        ]:
            annotationDict[child]["BQB_HAS_VERSION"] = annotationDict[parent][
                annotationLabel
            ]
        elif annotationLabel in ["BQB_HAS_PART"]:
            annotationDict[child][annotationLabel] = annotationDict[parent][
                annotationLabel
            ]


def updateFromChild(parent, child, annotationDict):
    for annotationLabel in annotationDict[child]:
        if annotationLabel in [
            "BQB_IS_VERSION_OF",
            "BQB_IS",
            "BQB_HAS_VERSION",
            "BQB_IS_HOMOLOG_TO",
        ]:
            annotationDict[parent]["BQB_HAS_VERSION"] = annotationDict[child][
                annotationLabel
            ]


# IS_HOMOLOG_TO
def updateFromComplex(complexMolecule, sct, annotationDict, annotationToSpeciesDict):
    localSpeciesDict = {}
    unmatchedReactants = []
    unmatchedAnnotations = []
    for constituentElement in sct[complexMolecule][0]:
        flag = False
        if len(annotationDict[constituentElement]) > 0:
            for annotation in annotationDict[constituentElement]:
                if annotation in [
                    "BQB_IS_VERSION_OF",
                    "BQB_IS",
                    "BQB_HAS_VERSION",
                    "BQB_IS_HOMOLOG_TO",
                    "BQM_IS",
                ]:
                    flag = True
                    for individualAnnotation in annotationDict[constituentElement][
                        annotation
                    ]:
                        localSpeciesDict[individualAnnotation] = constituentElement
                        localSpeciesDict[constituentElement] = individualAnnotation
            if flag:
                continue

        if constituentElement in annotationToSpeciesDict:
            localSpeciesDict[constituentElement] = annotationToSpeciesDict[
                constituentElement
            ]
            localSpeciesDict[
                annotationToSpeciesDict[constituentElement]
            ] = constituentElement
        else:
            unmatchedReactants.append(constituentElement)

    for annotationType in annotationDict[complexMolecule]:
        if annotationType in ["BQB_HAS_VERSION", "BQB_HAS_PART"]:
            for constituentAnnotation in annotationDict[complexMolecule][
                annotationType
            ]:
                if constituentAnnotation not in localSpeciesDict:
                    unmatchedAnnotations.append(constituentAnnotation)
    if len(set(unmatchedReactants)) == 1 and len(set(unmatchedAnnotations)) == 1:
        localSpeciesDict[unmatchedReactants[0]] = unmatchedAnnotations[0]
        localSpeciesDict[unmatchedAnnotations[0]] = unmatchedReactants[0]
        annotationDict[unmatchedReactants[0]]["BQB_IS_VERSION_OF"] = [
            unmatchedAnnotations[0]
        ]

    elif len(unmatchedReactants) > 0 or len(unmatchedAnnotations) > 0:
        # annotate from database names
        print "**//", complexMolecule, unmatchedReactants, unmatchedAnnotations

    for element in localSpeciesDict:
        if element not in annotationToSpeciesDict:
            annotationToSpeciesDict[element] = localSpeciesDict[element]


def updateFromComponents(complexMolecule, sct, annotationDict, annotationToSpeciesDict):
    localSpeciesDict = defaultdict(set)
    unmatchedReactants = []
    for constituentElement in sct[complexMolecule][0]:
        flag = False
        if complexMolecule == "G_sub_q_endsub__alpha__beta__gamma_":
            print constituentElement

        if len(annotationDict[constituentElement]) > 0:
            if complexMolecule == "G_sub_q_endsub__alpha__beta__gamma_":
                print constituentElement, annotationDict[constituentElement]

            for annotation in annotationDict[constituentElement]:
                if annotation in [
                    "BQB_IS_VERSION_OF",
                    "BQB_IS",
                    "BQB_HAS_VERSION",
                    "BQB_HAS_PART",
                    "BQB_IS_HOMOLOG_TO",
                    "BQM_IS",
                ]:
                    for individualAnnotation in annotationDict[constituentElement][
                        annotation
                    ]:
                        # localSpeciesDict[individualAnnotation] = constituentElement
                        localSpeciesDict[constituentElement].add(individualAnnotation)
                        flag = True
        if not flag:
            unmatchedReactants.append(constituentElement)

    for element in localSpeciesDict:
        annotationDict[complexMolecule]["BQB_HAS_PART"].extend(
            list(localSpeciesDict[element])
        )


def buildAnnotationTree(annotationDict, sct, database):
    annotationToSpeciesDict = {}
    for element in database.weights:
        if len(sct[element[0]]) > 0:
            if len(sct[element[0]][0]) == 1:
                buildingBlock = sct[element[0]][0][0]
                if len(annotationDict[element[0]]) == 0:
                    if len(annotationDict[buildingBlock]) > 0:
                        updateFromParent(element[0], buildingBlock, annotationDict)
                if len(annotationDict[buildingBlock]) == 0:
                    if len(annotationDict[element[0]]) > 0:
                        updateFromChild(buildingBlock, element[0], annotationDict)
            elif len(sct[element[0]][0]) > 1:
                if len(annotationDict[element[0]]) == 0:
                    updateFromComponents(
                        element[0], sct, annotationDict, annotationToSpeciesDict
                    )
                else:
                    if (
                        "BQB_HAS_VERSION" in annotationDict[element[0]]
                        or "BQB_HAS_PART" in annotationDict[element[0]]
                    ):
                        updateFromComplex(
                            element[0], sct, annotationDict, annotationToSpeciesDict
                        )
                    else:
                        updateFromComponents(
                            element[0], sct, annotationDict, annotationToSpeciesDict
                        )
            #        annotationdict[element[0]]
            # for buildingBlock in sct[element[0]][0]:
            #    print '\t',buildingBlock,annotationDict[buildingBlock]


def speciesAnnotationsToSBML(sbmlDocument, annotationDict, speciesNameDict):
    """
    Receives a series of annotations associated with their associated species
    and fills in a corresponding sbmlDocument with this information
    """
    for species in sbmlDocument.getModel().getListOfSpecies():
        transformedName = speciesNameDict[species.getName()]
        if len(annotationDict[transformedName]) == 0:
            continue
        for element in annotationDict[transformedName]:

            term = libsbml.CVTerm()
            if element.startswith("BQB"):
                term.setQualifierType(libsbml.BIOLOGICAL_QUALIFIER)
                term.setBiologicalQualifierType(bioqual.index(element))
            else:
                term.setQualifierType(libsbml.MODEL_QUALIFIER)
                term.setModelQualifierType(modqual.index(element))
            for annotation in annotationDict[transformedName][element]:
                term.addResource(annotation)
            species.addCVTerm(term)

        annotation = libsbml.RDFAnnotationParser.createAnnotation()
        cvterms = libsbml.RDFAnnotationParser.createCVTerms(species)
        rdfAnnotation = libsbml.RDFAnnotationParser.createRDFAnnotation()
        if cvterms:
            rdfAnnotation.addChild(cvterms)
        else:
            print species
        annotation.addChild(rdfAnnotation)
        species.setAnnotation(annotation)


actionSboDictionary = {
    "StateChange": "http://identifiers.org/biomodels.sbo/SBO:0000464",
    "DeleteBond": "http://identifiers.org/biomodels.sbo/SBO:0000180",
    "AddBond": "http://identifiers.org/biomodels.sbo/SBO:0000342",
    "ChangeCompartment": "http://identifiers.org/biomodels.sbo/SBO:0000185",
}


def buildReactionAnnotationDict(rules):
    sboDict = defaultdict(lambda: defaultdict(list))
    for rule in rules:
        actions = [x.action for x in rule[0].actions]
        if "Add" not in actions and "Delete" not in actions:
            sboDict[rule[0].label]["BQB_IS_VERSION_OF"] = [
                actionSboDictionary[x] for x in set(actions)
            ]
    return sboDict


def reactionAnnotationsToSBML(sbmlDocument, annotationDict):
    """
    Receives a series of annotations associated with their associated species
    and fills in a corresponding sbmlDocument with this information
    """
    for reaction in sbmlDocument.getModel().getListOfReactions():
        transformedName = reaction.getName()
        if len(annotationDict[transformedName]) == 0:
            continue
        for element in annotationDict[transformedName]:
            term = libsbml.CVTerm()
            if element.startswith("BQB"):
                term.setQualifierType(libsbml.BIOLOGICAL_QUALIFIER)
                term.setBiologicalQualifierType(bioqual.index(element))
            else:
                term.setQualifierType(libsbml.MODEL_QUALIFIER)
                term.setModelQualifierType(modqual.index(element))
            for annotation in annotationDict[transformedName][element]:
                term.addResource(annotation)
            reaction.addCVTerm(term)

        annotation = libsbml.RDFAnnotationParser.createAnnotation()
        cvterms = libsbml.RDFAnnotationParser.createCVTerms(reaction)
        rdfAnnotation = libsbml.RDFAnnotationParser.createRDFAnnotation()
        rdfAnnotation.addChild(cvterms)
        annotation.addChild(rdfAnnotation)
        reaction.setAnnotation(annotation)


def obtainSCT(fileName, reactionDefinitions, useID, namingConventions):
    """
    one of the library's main entry methods. Process data from a file
    to obtain the species composition table, a dictionary describing
    the chemical history of different elements in the system
    """
    logMess.log = []
    logMess.counter = -1
    reader = libsbml.SBMLReader()
    document = reader.readSBMLFromFile(fileName)

    parser = SBML2BNGL(document.getModel(), useID)

    database = structures.Databases()
    database.forceModificationFlag = True
    database.softConstraints = True
    database.parser = parser
    database = mc.createSpeciesCompositionGraph(
        parser,
        database,
        reactionDefinitions,
        namingConventions,
        speciesEquivalences=None,
        bioGridFlag=False,
    )

    return database.prunnedDependencyGraph, database, document, parser.speciesDictionary


import tempfile


def writeSBML(document, fileName):
    writer = libsbml.SBMLWriter()
    writer.writeSBMLToFile(document, fileName)


def createDataStructures(bnglContent):
    """
    create an atomized biomodels in a temporary file to obtain relevant
    bng information
    """

    pointer = tempfile.mkstemp(suffix=".bngl", text=True)
    with open(pointer[1], "w") as f:
        f.write(bnglContent)
    retval = os.getcwd()
    os.chdir(tempfile.tempdir)
    consoleCommands.bngl2xml(pointer[1])
    xmlfilename = ".".join(pointer[1].split(".")[0:-1]) + ".xml"
    os.chdir(retval)
    return readBNGXML.parseXML(xmlfilename)


def expandAnnotation(fileName, bnglFile):

    sct, database, sbmlDocument, _ = obtainSCT(
        fileName,
        "config/reactionDefinitions.json",
        False,
        "config/namingConventions.json",
    )
    annotationDict, speciesNameDict = buildAnnotationDict(sbmlDocument)
    buildAnnotationTree(annotationDict, sct, database)
    speciesAnnotationsToSBML(sbmlDocument, annotationDict, speciesNameDict)
    # species, rules, par = createDataStructures(bnglFile)
    # reactionAnnotationDict = buildReactionAnnotationDict(rules)
    # reactionAnnotationsToSBML(sbmlDocument,reactionAnnotationDict)
    # reactionAnnotationsToSBML(sbmlDocument,reactionAnnotation)

    # reactionAnnotationsToSBML(sbmlDocument)
    writer = libsbml.SBMLWriter()
    return writer.writeSBMLToString(sbmlDocument)


import progressbar


def batchExtensionProcess(directory, outputDir):
    testFiles = getFiles(directory, "xml")
    progress = progressbar.ProgressBar()

    targetFiles = getFiles(outputDir, "xml")
    for fileIdx in progress(range(len(testFiles))):
        file = testFiles[fileIdx]
        if file in [
            "/home/proto/workspace/RuleWorld/atomizer/SBMLparser/annotationsRemoved2/BIOMD0000000223.xml",
            "/home/proto/workspace/RuleWorld/atomizer/SBMLparser/annotationsRemoved2/BIOMD0000000488.xml",
            "/home/proto/workspace/RuleWorld/atomizer/SBMLparser/annotationsRemoved2/BIOMD0000000293.xml",
            "/home/proto/workspace/RuleWorld/atomizer/SBMLparser/annotationsRemoved2/BIOMD0000000472.xml",
            "/home/proto/workspace/RuleWorld/atomizer/SBMLparser/annotationsRemoved2/BIOMD0000000255.xml",
            "/home/proto/workspace/RuleWorld/atomizer/SBMLparser/annotationsRemoved2/BIOMD0000000424.xml",
            "/home/proto/workspace/RuleWorld/atomizer/SBMLparser/annotationsRemoved2/BIOMD0000000439.xml",
            "/home/proto/workspace/RuleWorld/atomizer/SBMLparser/annotationsRemoved2/BIOMD0000000416.xml",
            "/home/proto/workspace/RuleWorld/atomizer/SBMLparser/annotationsRemoved2/BIOMD0000000182.xml",
            "/home/proto/workspace/RuleWorld/atomizer/SBMLparser/annotationsRemoved2/BIOMD0000000161.xml",
            "/home/proto/workspace/RuleWorld/atomizer/SBMLparser/annotationsRemoved2/BIOMD0000000504.xml",
        ]:
            continue
        if (
            "/home/proto/workspace/RuleWorld/atomizer/SBMLparser/annotationsExpanded2/{0}".format(
                file.split("/")[-1]
            )
            in targetFiles
        ):
            continue
        print file
        sbmlInfo = expandAnnotation(file, "")
        outputFile = os.path.join(outputDir, file.split("/")[-1])

        with open(outputFile, "w") as f:
            f.write(sbmlInfo)


def defineConsole():
    parser = argparse.ArgumentParser(description="SBML to BNGL translator")
    parser.add_argument(
        "-i", "--input-file", type=str, help="input SBML file", required=True
    )
    parser.add_argument(
        "-o", "--output-file", type=str, help="output SBML file", required=True
    )
    return parser


if __name__ == "__main__":
    batchExtensionProcess("annotationsRemoved2", "annotationsExpanded2")

    # parser = defineConsole()
    # namespace = parser.parse_args()
    # input_file = '/home/proto/workspace/bionetgen/parsers/SBMLparser/XMLExamples/curated/BIOMD%010i.xml' % 19
    # expandedString = expandAnnotation(namespace.input_file, '')
    # print 'Writing extended annotation SBML to {0}'.format(namespace.output_file)
    # with open(namespace.output_file,'w') as f:
    #     f.write(expandedString)
    # outputFileName = '.'.join(fileName.split('.')[0:-1]) + '_withAnnotations.xml'
    # writeSBML(sbmlDocument,outputFileName)
