# -*- coding: utf-8 -*-
"""
Created on Thu Mar 22 13:11:38 2012

@author: proto
"""

import enum
import imp
from pyparsing import Word, Suppress, Optional, alphanums, Group, ZeroOrMore
import numpy as np
import json
import itertools
import bionetgen.atomizer.utils.structures as st
from copy import deepcopy, copy
from . import detectOntology
import re
import difflib
from bionetgen.atomizer.utils.util import logMess
from collections import defaultdict
import itertools
import math
from collections import Counter
import re
import os
from bionetgen.atomizer.utils.util import pmemoize as memoize

"""
This file in general classifies rules according to the information contained in
the json config file for classyfying rules according to their reactants/products
"""


@memoize
def get_close_matches(match, dataset, cutoff=0.6):
    return difflib.get_close_matches(match, dataset, cutoff=cutoff)


@memoize
def sequenceMatcher(a, b):
    """
    compares two strings ignoring underscores
    """
    return difflib.SequenceMatcher(lambda x: x == "_", a, b).ratio()


name = Word(alphanums + "_-") + ":"
species = (
    Word(alphanums + "_" + ":#-")
    + Suppress("()")
    + Optional(Suppress("@" + Word(alphanums + "_-")))
) + ZeroOrMore(
    Suppress("+")
    + Word(alphanums + "_" + ":#-")
    + Suppress("()")
    + Optional(Suppress("@" + Word(alphanums + "_-")))
)
rate = Word("-" + alphanums + "()")
grammar = Suppress(Optional(name)) + (
    (Group(species) | "0")
    + Suppress(Optional("<") + "->")
    + (Group(species) | "0")
    + Suppress(rate)
)


@memoize
def parseReactions(reaction, specialSymbols=""):
    if reaction.startswith("#"):
        return None
    result = grammar.parseString(reaction).asList()
    if len(result) < 2:
        result = [result, []]
    if "<->" in reaction and len(result[0]) == 1 and len(result[1]) == 2:
        result.reverse()
    return result


def addToDependencyGraph(dependencyGraph, label, value):
    if label not in dependencyGraph:
        dependencyGraph[label] = []
    if value not in dependencyGraph[label] and value != []:
        dependencyGraph[label].append(value)


class SBMLAnalyzer:
    def __init__(
        self,
        modelParser,
        configurationFile,
        namingConventions,
        speciesEquivalences=None,
        conservationOfMass=True,
    ):
        self.modelParser = modelParser
        self.configurationFile = configurationFile
        self.namingConventions = detectOntology.loadOntology(namingConventions)
        self.userNamingConventions = copy(self.namingConventions)
        self.speciesEquivalences = speciesEquivalences
        self.userEquivalencesDict = None
        self.lexicalSpecies = []
        self.conservationOfMass = conservationOfMass

    def distanceToModification(self, particle, modifiedElement, translationKeys):
        posparticlePos = [
            m.start() + len(particle) for m in re.finditer(particle, modifiedElement)
        ]
        preparticlePos = [m.start() for m in re.finditer(particle, modifiedElement)]
        keyPos = [m.start() for m in re.finditer(translationKeys, modifiedElement)]
        distance = [abs(y - x) for x in posparticlePos for y in keyPos]
        distance.extend([abs(y - x) for x in preparticlePos for y in keyPos])
        distance.append(9999)
        return min(distance)

    def fuzzyArtificialReaction(self, baseElements, modifiedElement, molecules):
        """
        in case we don't know how a species is composed but we know its base
        elements, try to get it by concatenating its basic reactants
        """
        import collections

        compare = lambda x, y: collections.Counter(x) == collections.Counter(y)
        (
            equivalenceTranslator,
            translationKeys,
            conventionDict,
        ) = self.processNamingConventions2(molecules)
        indirectEquivalenceTranslator = {x: [] for x in equivalenceTranslator}
        self.processFuzzyReaction(
            [baseElements, modifiedElement],
            translationKeys,
            conventionDict,
            indirectEquivalenceTranslator,
        )
        newBaseElements = baseElements
        for modification in indirectEquivalenceTranslator:
            for element in indirectEquivalenceTranslator[modification]:
                newBaseElements = [
                    element[2][1] if x == element[2][0] else x for x in newBaseElements
                ]
        if compare(baseElements, newBaseElements):
            return None
        return newBaseElements

    def analyzeSpeciesModification2(
        self, baseElement, modifiedElement, partialAnalysis
    ):
        """
        A method to read modifications within complexes.

        """

        def index_min(values):
            return min(range(len(values)), key=values.__getitem__)

        (
            equivalenceTranslator,
            translationKeys,
            conventionDict,
        ) = self.processNamingConventions2([baseElement, modifiedElement])

        differencePosition = [
            (i, x)
            for i, x in enumerate(difflib.ndiff(baseElement, modifiedElement))
            if x.startswith("+")
        ]
        tmp = ""
        lastIdx = 0
        newDifferencePosition = []
        for i in range(len(differencePosition)):
            tmp += differencePosition[i][1][-1]
            if tmp in translationKeys:
                newDifferencePosition.append(
                    (
                        (differencePosition[lastIdx][0] + differencePosition[i][0]) / 2,
                        tmp,
                    )
                )
                tmp = ""
                lastIdx = i

        differencePosition = newDifferencePosition

        if len(differencePosition) == 0:
            return None, None, None
        sortedPartialAnalysis = sorted(partialAnalysis, key=len, reverse=True)
        tokenPosition = []
        tmpModifiedElement = modifiedElement
        for token in sortedPartialAnalysis:
            sequenceMatcher = difflib.SequenceMatcher(None, token, tmpModifiedElement)
            # sequenceMatcher2 = difflib.SequenceMatcher(None,token,baseElement)
            modifiedMatchingBlocks = [
                m.span() for m in re.finditer(token, tmpModifiedElement)
            ]
            baseMatchingBlocks = [m.span() for m in re.finditer(token, baseElement)]
            # matchingBlocks = [x for x in modifiedMatchingBlocks for y in baseMatching Blocks if ]
            if len(modifiedMatchingBlocks) > 0 and len(baseMatchingBlocks) > 0:
                # select the matching block with the lowest distance to the base matching block
                matchingBlockIdx = index_min(
                    [
                        min(
                            [
                                abs((y[1] + y[0]) / 2 - (x[1] + x[0]) / 2)
                                for y in baseMatchingBlocks
                            ]
                        )
                        for x in modifiedMatchingBlocks
                    ]
                )
                matchingBlock = modifiedMatchingBlocks[matchingBlockIdx]
                tmpModifiedElement = list(tmpModifiedElement)
                for idx in range(matchingBlock[0], matchingBlock[1]):
                    tmpModifiedElement[idx] = "_"
                tmpModifiedElement = "".join(tmpModifiedElement)
                tokenPosition.append((matchingBlock[0], matchingBlock[1] - 1))
            else:
                # try fuzzy search
                sequenceMatcher = difflib.SequenceMatcher(
                    None, token, tmpModifiedElement
                )
                match = "".join(
                    tmpModifiedElement[j : j + n]
                    for i, j, n in sequenceMatcher.get_matching_blocks()
                    if n
                )

                if (len(match)) / float(len(token)) < 0.8:
                    tokenPosition.append([999999999])
                else:
                    tmp = [
                        i
                        for i, y in enumerate(difflib.ndiff(token, tmpModifiedElement))
                        if not y.startswith("+")
                    ]
                    if tmp[-1] - tmp[0] > len(token) + 5:
                        tokenPosition.append([999999999])
                        continue
                    tmpModifiedElement = list(tmpModifiedElement)
                    for idx in tmp:
                        if idx < len(tmpModifiedElement):
                            tmpModifiedElement[idx] = "_"
                    tmpModifiedElement = "".join(tmpModifiedElement)
                    tmp = [tmp[0], tmp[-1] - 1]
                    tokenPosition.append(tmp)

        intersection = []
        for difference in differencePosition:
            distance = []
            for token in tokenPosition:
                distance.append(
                    min([abs(difference[0] - subtoken) for subtoken in token])
                )
            closestToken = sortedPartialAnalysis[index_min(distance)]
            # if difference[1] in conventionDict:
            intersection.append([difference[1], closestToken, min(distance)])
        minimumToken = min(intersection, key=lambda x: x[2])

        if intersection:
            return minimumToken[1], translationKeys, equivalenceTranslator
        return None, None, None

    def analyzeSpeciesModification(self, baseElement, modifiedElement, partialAnalysis):
        """
        a method for trying to read modifications within complexes
        This is only possible once we know their internal structure
        (this method is called after the creation and resolving of the dependency
        graph)
        """
        (
            equivalenceTranslator,
            translationKeys,
            conventionDict,
        ) = self.processNamingConventions2([baseElement, modifiedElement])
        scores = []
        if len(translationKeys) == 0:
            """
            there's no clear lexical path between reactant and product
            """
            return None, None, None
        for particle in partialAnalysis:
            distance = 9999
            comparisonElement = max(baseElement, modifiedElement, key=len)
            if re.search("(_|^){0}(_|$)".format(particle), comparisonElement) == None:
                distance = self.distanceToModification(
                    particle, comparisonElement, translationKeys[0]
                )
                score = difflib.ndiff(particle, modifiedElement)
            else:
                # FIXME: make sure we only do a search on those variables that are viable
                # candidates. this is once again fuzzy string matchign. there should
                # be a better way of doing this with difflib
                permutations = set(
                    [
                        "_".join(x)
                        for x in itertools.permutations(partialAnalysis, 2)
                        if x[0] == particle
                    ]
                )
                if all([x not in modifiedElement for x in permutations]):
                    distance = self.distanceToModification(
                        particle, comparisonElement, translationKeys[0]
                    )
                    score = difflib.ndiff(particle, modifiedElement)
                # FIXME:tis is just an ad-hoc parameter in terms of how far a mod is from a species name
                # use something better
            if distance < 4:
                scores.append([particle, distance])
        if len(scores) > 0:
            winner = scores[[x[1] for x in scores].index(min([x[1] for x in scores]))][
                0
            ]
        else:
            winner = None
        if winner:
            return winner, translationKeys, equivalenceTranslator
        return None, None, None

    def findMatchingModification(self, particle, species):
        @memoize
        def findMatchingModificationHelper(particle, species):
            difference = difflib.ndiff(species, particle)
            differenceList = tuple([x for x in difference if "+" in x])
            if differenceList in self.namingConventions["patterns"]:
                return [self.namingConventions["patterns"][differenceList]]
            fuzzyKey = "".join([x[2:] for x in differenceList])
            differenceList = self.testAgainstExistingConventions(
                fuzzyKey, self.namingConventions["modificationList"]
            )
            # can we state the modification as the combination of multiple modifications
            if differenceList:
                classificationList = []
                for x in differenceList[0]:
                    differenceKey = tuple(["+ {0}".format(letter) for letter in x])
                    classificationList.append(
                        self.namingConventions["patterns"][differenceKey]
                    )
                return classificationList
            return None

        return findMatchingModificationHelper(particle, species)

    def greedyModificationMatching(self, speciesString, referenceSpecies):
        """
        recursive function trying to map a given species string to a string permutation of the strings in reference species
        >>> sa = SBMLAnalyzer(None,'./config/reactionDefinitions.json','./config/namingConventions.json')
        >>> sorted(sa.greedyModificationMatching('EGF_EGFR',['EGF','EGFR']))
        ['EGF', 'EGFR']
        >>> sorted(sa.greedyModificationMatching('EGF_EGFR_2_P_Grb2',['EGF','EGFR','EGF_EGFR_2_P','Grb2']))
        ['EGF_EGFR_2_P', 'Grb2']
        >>> sorted(sa.greedyModificationMatching('A_B_C_D',['A','B','C','C_D','A_B_C','A_B']))
        ['A_B', 'C_D']
        """
        bestMatch = ["", 0]
        finalMatches = []
        blacklist = []
        while len(blacklist) < len(referenceSpecies):
            localReferenceSpecies = [
                x
                for x in referenceSpecies
                if x not in blacklist and len(x) <= len(speciesString)
            ]
            for species in localReferenceSpecies:
                if (
                    species in speciesString
                    and len(species) > bestMatch[1]
                    and species != speciesString
                ):
                    bestMatch = [species, len(species)]
            if bestMatch != ["", 0]:
                result = self.greedyModificationMatching(
                    speciesString.replace(bestMatch[0], ""), referenceSpecies
                )
                finalMatches = [bestMatch[0]]
                if result == -1:
                    finalMatches = []
                    blacklist.append(bestMatch[0])
                    bestMatch = ["", 0]
                    continue
                elif result != -2:
                    finalMatches.extend(result)
                break
            elif len([x for x in speciesString if x != "_"]) > 0:
                return -1
            else:
                return -2

        return finalMatches

    def findClosestModification(
        self, particles, species, annotationDict, originalDependencyGraph
    ):
        """
        maps a set of particles to the complete set of species using lexical analysis. This step is done
        independent of the reaction network.
        """

        # ASS2019 - in Python3 species is a dictKey object and can't be marshaled,
        # this should be both p2 and p3 compatible
        species = list(species)
        equivalenceTranslator = {}
        dependencyGraph = {}
        localSpeciesDict = defaultdict(lambda: defaultdict(list))

        def analyzeByParticle(
            splitparticle,
            species,
            equivalenceTranslator=equivalenceTranslator,
            dependencyGraph=dependencyGraph,
        ):
            basicElements = []
            composingElements = []
            splitpindex = -1
            while (splitpindex + 1) < len(splitparticle):
                splitpindex += 1
                splitp = splitparticle[splitpindex]
                if splitp in species:
                    closestList = [splitp]
                    similarList = get_close_matches(splitp, species)
                    similarList = [
                        x for x in similarList if x != splitp and len(x) < len(splitp)
                    ]
                    similarList = [[x, splitp] for x in similarList]
                    if len(similarList) > 0:
                        for similarity in similarList:

                            # compare close lexical proximity
                            fuzzyList = self.processAdHocNamingConventions(
                                similarity[0],
                                similarity[1],
                                localSpeciesDict,
                                False,
                                species,
                            )
                            for reaction, tag, modifier in fuzzyList:
                                if modifier != None and all(
                                    ["-" not in x for x in modifier]
                                ):
                                    logMess(
                                        "INFO:LAE001",
                                        "Lexical relationship inferred between \
                                    {0}, user information confirming it is required".format(
                                            similarity
                                        ),
                                    )

                else:
                    closestList = get_close_matches(splitp, species)
                    closestList = [x for x in closestList if len(x) < len(splitp)]
                # if theres nothing in the species list i can find a lexical
                # neighbor from, then try to create one based on my two
                # positional neighbors
                if closestList == []:
                    flag = True
                    # do i get something by merging with the previous component?
                    if len(composingElements) > 0:
                        tmp, tmp2 = analyzeByParticle(
                            [composingElements[-1] + "_" + splitp], species
                        )
                        if tmp != [] and tmp2 != []:
                            flag = False
                            splitp = composingElements[-1] + "_" + splitp
                            composingElements.pop()
                            closestList = tmp
                            (
                                localEquivalenceTranslator,
                                _,
                                _,
                            ) = self.processNamingConventions2([tmp[0], tmp2[0]])
                            for element in localEquivalenceTranslator:
                                if element not in equivalenceTranslator:
                                    equivalenceTranslator[element] = []
                                equivalenceTranslator[element].extend(
                                    localEquivalenceTranslator[element]
                                )
                                for instance in localEquivalenceTranslator[element]:
                                    addToDependencyGraph(
                                        dependencyGraph, instance[1], [instance[0]]
                                    )
                    # do i get something by merging with the next component?
                    if flag and splitpindex + 1 != len(splitparticle):
                        tmp, tmp2 = analyzeByParticle(
                            [splitp + "_" + splitparticle[splitpindex + 1]], species
                        )
                        if tmp != [] and tmp2 != []:
                            splitp = splitp + "_" + splitparticle[splitpindex + 1]
                            splitpindex += 1
                            closestList = tmp
                            (
                                localEquivalenceTranslator,
                                _,
                                _,
                            ) = self.processNamingConventions2([tmp[0], tmp2[0]])
                            for element in localEquivalenceTranslator:
                                if element not in equivalenceTranslator:
                                    equivalenceTranslator[element] = []
                                equivalenceTranslator[element].append(
                                    localEquivalenceTranslator[element]
                                )
                                for instance in localEquivalenceTranslator[element]:
                                    addToDependencyGraph(
                                        dependencyGraph, instance[1], [instance[0]]
                                    )

                        else:
                            return [], []
                    elif flag:
                        return [], []
                basicElements.append(min(closestList, key=len))
                # if what i have is a known compound just add it
                if splitp in species:
                    composingElements.append(splitp)
                # if not create it
                else:
                    closestList = get_close_matches(splitp, species)
                    closestList = [x for x in closestList if len(x) < len(splitp)]
                    flag = False
                    for element in closestList:
                        (
                            localEquivalenceTranslator,
                            _,
                            _,
                        ) = self.processNamingConventions2([element, splitp])
                        if len(list(localEquivalenceTranslator.keys())) == 0:
                            basicElements = []
                            composingElements = []
                        for element in localEquivalenceTranslator:
                            if element not in equivalenceTranslator:
                                equivalenceTranslator[element] = []
                            equivalenceTranslator[element].append(
                                localEquivalenceTranslator[element]
                            )
                            for instance in localEquivalenceTranslator[element]:
                                addToDependencyGraph(
                                    dependencyGraph, instance[1], [instance[0]]
                                )
                            flag = True
                    if flag:
                        composingElements.append(splitp)
            return basicElements, composingElements

        additionalHandling = []

        # lexical handling
        for particle in sorted(particles, key=len):
            composingElements = []
            basicElements = []
            # can you break it down into small bites?
            if "_" in particle:
                splitparticle = particle.split("_")
                # print('---',splitparticle)
                splitparticle = [x for x in splitparticle if x]
                # print(splitparticle)

                basicElements, composingElements = analyzeByParticle(
                    splitparticle, species
                )

                if basicElements == composingElements and basicElements:
                    closeMatches = get_close_matches(particle, species)
                    matches = [
                        x
                        for x in closeMatches
                        if len(x) < len(particle) and len(x) >= 3
                    ]
                    for match in matches:
                        difference = difflib.ndiff(match, particle)
                        differenceList = tuple([x for x in difference if "+" in x])
                        if differenceList in self.namingConventions["patterns"]:
                            logMess(
                                "INFO:LAE005",
                                "matching {0}={1}".format(particle, [match]),
                            )
                            addToDependencyGraph(dependencyGraph, particle, [match])
                    if len(matches) > 0:
                        continue

                elif (
                    particle not in composingElements
                    and composingElements != []
                    and all([x in species for x in composingElements])
                ):
                    addToDependencyGraph(dependencyGraph, particle, composingElements)
                    for element in composingElements:
                        if element not in dependencyGraph:
                            addToDependencyGraph(dependencyGraph, element, [])
                        if element not in particles:
                            additionalHandling.append(element)
                    continue
                else:
                    for basicElement in basicElements:
                        if basicElement in particle and basicElement != particle:
                            fuzzyList = self.processAdHocNamingConventions(
                                basicElement, particle, localSpeciesDict, False, species
                            )
                            if self.testAgainstExistingConventions(
                                fuzzyList[0][1],
                                self.namingConventions["modificationList"],
                            ):
                                addToDependencyGraph(
                                    dependencyGraph, particle, [basicElement]
                                )
                                logMess(
                                    "INFO:LAE005",
                                    "{0} can be mapped to {1} through existing naming conventions".format(
                                        particle, [basicElement]
                                    ),
                                )
                                break
                    continue
            # if bottom up doesn't work try a top down approach
            for comparisonParticle in particles:
                if particle == comparisonParticle:
                    continue
                # try to map remaining orphaned molecules to each other based on simple, but known modifications
                if comparisonParticle in particle:
                    fuzzyList = self.processAdHocNamingConventions(
                        particle, comparisonParticle, localSpeciesDict, False, species
                    )
                    if self.testAgainstExistingConventions(
                        fuzzyList[0][1], self.namingConventions["modificationList"]
                    ):

                        if (
                            particle in annotationDict
                            and comparisonParticle in annotationDict
                        ):
                            baseSet = set(
                                [
                                    y
                                    for x in annotationDict[particle]
                                    for y in annotationDict[particle][x]
                                ]
                            )
                            modSet = set(
                                [
                                    y
                                    for x in annotationDict[comparisonParticle]
                                    for y in annotationDict[comparisonParticle][x]
                                ]
                            )
                            if len(baseSet.intersection(modSet)) == 0:
                                baseDB = set(
                                    [
                                        x.split("/")[-2]
                                        for x in baseSet
                                        if "identifiers.org" in x
                                    ]
                                )
                                modDB = set(
                                    [
                                        x.split("/")[-2]
                                        for x in modSet
                                        if "identifiers.org" in x
                                    ]
                                )
                                # we stil ahve to check that they both reference the same database
                                if len(baseDB.intersection(modDB)) > 0:

                                    logMess(
                                        "ERROR:ANN202",
                                        "{0}:{1}:can be mapped through naming conventions but the annotation information does not match".format(
                                            particle, comparisonParticle
                                        ),
                                    )
                                    continue

                        addToDependencyGraph(
                            dependencyGraph, particle, [comparisonParticle]
                        )
                        logMess(
                            "INFO:LAE005",
                            "{0} can be mapped to {1} through existing naming conventions".format(
                                particle, [comparisonParticle]
                            ),
                        )
                        break
                else:
                    common_root = detectOntology.findLongestSubstring(
                        particle, comparisonParticle
                    )
                    # some arbitrary threshold of what makes a good minimum lenght for the common root
                    if (
                        len(common_root) > 0
                        and common_root not in originalDependencyGraph
                    ):

                        fuzzyList = self.processAdHocNamingConventions(
                            common_root,
                            comparisonParticle,
                            localSpeciesDict,
                            False,
                            species,
                        )
                        fuzzyList2 = self.processAdHocNamingConventions(
                            common_root, particle, localSpeciesDict, False, species
                        )

                        particleMap = self.testAgainstExistingConventions(
                            fuzzyList[0][1], self.namingConventions["modificationList"]
                        )
                        compParticleMap = (
                            fuzzyList2,
                            self.testAgainstExistingConventions(
                                fuzzyList2[0][1],
                                self.namingConventions["modificationList"],
                            ),
                        )
                        if particleMap and compParticleMap:
                            if (
                                particle in annotationDict
                                and comparisonParticle in annotationDict
                            ):
                                baseSet = set(
                                    [
                                        y
                                        for x in annotationDict[particle]
                                        for y in annotationDict[particle][x]
                                    ]
                                )
                                modSet = set(
                                    [
                                        y
                                        for x in annotationDict[comparisonParticle]
                                        for y in annotationDict[comparisonParticle][x]
                                    ]
                                )
                                if len(baseSet.intersection(modSet)) == 0:
                                    logMess(
                                        "ERROR:ANN202",
                                        "{0}:{1}:can be mapped through naming conventions but the annotation information does not match".format(
                                            particle, comparisonParticle
                                        ),
                                    )
                                    break
                            addToDependencyGraph(
                                dependencyGraph, particle, [common_root]
                            )
                            addToDependencyGraph(
                                dependencyGraph, comparisonParticle, [common_root]
                            )
                            addToDependencyGraph(dependencyGraph, common_root, [])

                            logMess(
                                "INFO:LAE006",
                                "{0}:{1}:can be mapped together through new common molecule {2} by existing naming conventions".format(
                                    particle, comparisonParticle, common_root
                                ),
                            )
                            break

        # if len(additionalHandling) > 0:
        # print(self.findClosestModification(set(additionalHandling),species))
        return dependencyGraph, equivalenceTranslator

    def loadConfigFiles(self, fileName):
        """
        the reactionDefinition file must contain the definitions of the basic reaction types
        we wnat to parse and what are the requirements of a given reaction type to be considered
        as such
        """
        reactionDefinition = ""
        if fileName is not None:
            if fileName == "":
                return []
            if os.path.isfile(fileName):
                with open(fileName, "r") as fp:
                    reactionDefinition_new = json.load(fp)
                # adjust for new file format and keep propagating the same
                # object format downstream so we don't have to deal with
                # downstream changes
                # let's start with binding interaction/complexDefinition block
                reactionDefinition = {}
                if "binding_interactions" in reactionDefinition_new:
                    reactionDefinition["complexDefinition"] = []
                    # convert new JSON format to old data format
                    # we'll need to make sure symmetrical ones are created
                    # this is a list of pairs
                    for binding_pair in reactionDefinition_new["binding_interactions"]:
                        first, second = binding_pair[0], binding_pair[1]
                        if isinstance(first, dict) or isinstance(second, dict):
                            # TODO: Implement dictionaries for binding partners in the future
                            raise NotImplementedError(
                                "Dictionaries for binding pairs are not implemented yet"
                            )

                        # let's deal with first
                        # first initalize the item or pull if it already exists
                        item = None
                        for ix, x in enumerate(reactionDefinition["complexDefinition"]):
                            if x[0] == first:
                                item = reactionDefinition["complexDefinition"].pop(ix)
                                break
                        if item is None:
                            item = [first, [[first]]]
                        item[1][0].append(second.lower())
                        item[1][0].append([])
                        reactionDefinition["complexDefinition"].append(item)

                        # now deal with second partner
                        # first initalize the item or pull if it already exists
                        item = None
                        for ix, x in enumerate(reactionDefinition["complexDefinition"]):
                            if x[0] == second:
                                item = reactionDefinition["complexDefinition"].pop(ix)
                                break
                        if item is None:
                            item = [second, [[second]]]
                        item[1][0].append(first.lower())
                        item[1][0].append([])
                        reactionDefinition["complexDefinition"].append(item)
                else:
                    reactionDefinition["complexDefinition"] = []
                # now deal with reaction definition block
                if "reactionDefinition" in reactionDefinition_new:
                    reactionDefinition["reactionDefinition"] = []
                    # convert new JSON format to old data format
                else:
                    reactionDefinition["reactionDefinition"] = []
                # deal with modifications
                if "modificationDefinition" in reactionDefinition_new:
                    # TODO: Change file format to be nicer?
                    reactionDefinition[
                        "modificationDefinition"
                    ] = reactionDefinition_new["modificationDefinition"]
                    # convert new JSON format to old data format
                else:
                    reactionDefinition["modificationDefinition"] = {}

                return reactionDefinition
        reactionDefinition = {
            "reactions": [
                [["S0", "S1"], ["S2"]],
                [["S2"], ["S0", "S1"]],
                [[], ["S0"]],
                [["S0"], []],
                [["S0", "S1", "S2"], ["S3"]],
                [["S3"], ["S0", "S1", "S2"]],
            ],
            "reactionsNames": [
                "Binding",
                "Binding",
                "Binding",
                "Binding",
                "Generation",
                "Decay",
                "Phosporylation",
                "Double-Phosporylation",
                "iMod",
                "mMod",
                "Ubiquitination",
            ],
            "definitions": [
                [{"r": [0]}, {"n": []}],
                [{"r": [1]}, {"n": []}],
                [{"r": [4]}, {"n": []}],
                [{"r": [5]}, {"n": []}],
                [{"r": [2]}],
                [{"r": [3]}],
                [{"n": [0]}],
                [{"n": []}],
                [{"n": []}],
                [{"n": []}],
                [{"n": []}],
            ],
        }
        return reactionDefinition

    def identifyReactions2(self, rule, reactionDefinition):
        """
        This method goes through the list of common reactions listed in ruleDictionary
        and tries to find how are they related according to the information in reactionDefinition
        """
        result = []
        for idx, element in enumerate(reactionDefinition["reactions"]):
            tmp1 = rule[0] if rule[0] not in ["0", ["0"]] else []
            tmp2 = rule[1] if rule[1] not in ["0", ["0"]] else []
            if len(tmp1) == len(element[0]) and len(tmp2) == len(element[1]):
                result.append(1)
            #            for (el1,el2) in (element[0],rule[0]):
            #                if element[0].count(el1) == element[]
            else:
                result.append(0)
        return result

    def species2Rules(self, rules):
        """
        This method goes through the rule list and classifies species tuples in a dictionary
        according to the reactions they appear in.
        """
        ruleDictionary = {}
        for idx, rule in enumerate(rules):
            reaction2 = rule  # list(parseReactions(rule))
            totalElements = [item for sublist in reaction2 for item in sublist]
            if tuple(totalElements) in ruleDictionary:
                ruleDictionary[tuple(totalElements)].append(idx)
            else:
                ruleDictionary[tuple(totalElements)] = [idx]
        return ruleDictionary

    def checkCompliance(self, ruleCompliance, tupleCompliance, ruleBook):
        """
        This method is mainly useful when a single reaction can be possibly classified
        in different ways, but in the context of its tuple partners it can only be classified
        as one
        """
        ruleResult = np.zeros(len(ruleBook))
        for validTupleIndex in np.nonzero(tupleCompliance):
            for index in validTupleIndex:
                for alternative in ruleBook[index]:
                    if "r" in alternative and np.any(
                        [ruleCompliance[temp] for temp in alternative["r"]]
                    ):
                        ruleResult[index] = 1
                        break
                    # check if just this is enough
                    if "n" in alternative:
                        ruleResult[index] = 1
                        break
        return ruleResult

    def levenshtein(self, s1, s2):
        l1 = len(s1)
        l2 = len(s2)

        matrix = [list(range(l1 + 1))] * (l2 + 1)
        for zz in range(l2 + 1):
            matrix[zz] = list(range(zz, zz + l1 + 1))
        for zz in range(0, l2):
            for sz in range(0, l1):
                if s1[sz] == s2[zz]:
                    matrix[zz + 1][sz + 1] = min(
                        matrix[zz + 1][sz] + 1, matrix[zz][sz + 1] + 1, matrix[zz][sz]
                    )
                else:
                    matrix[zz + 1][sz + 1] = min(
                        matrix[zz + 1][sz] + 1,
                        matrix[zz][sz + 1] + 1,
                        matrix[zz][sz] + 1,
                    )
        return matrix[l2][l1]

    def analyzeUserDefinedEquivalences(self, molecules, conventions):
        equivalences = {}
        smolecules = [x.strip("()") for x in molecules]
        modifiedElement = {}
        for convention in conventions:
            baseMol = []
            modMol = []
            for molecule in smolecules:
                if convention[0] in molecule and convention[1] not in molecule:
                    baseMol.append(molecule)
                elif convention[1] in molecule:
                    modMol.append(molecule)
            if convention[2] not in equivalences:
                equivalences[convention[2]] = []
            equivalences[convention[2]].append((convention[0], convention[1]))
            if convention[0] not in modifiedElement:
                modifiedElement[convention[0]] = []
            modifiedElement[convention[0]].append((convention[0], convention[1]))
            """
            for mol1 in baseMol:
                for mol2 in modMol:
                    score = self.levenshtein(mol1,mol2)
                    if score == self.levenshtein(convention[0],convention[1]):
                        equivalences[convention[2]].append((mol1,mol2))
                        modifiedElement[convention[0]].append((mol1,mol2))
                        break
            """
        return equivalences, modifiedElement

    def processNamingConventions2(self, molecules, threshold=4, onlyUser=False):

        # normal naming conventions
        strippedMolecules = [x.strip("()") for x in molecules]

        tmpTranslator = {}
        translationKeys = []
        conventionDict = {}

        # FIXME: This line contains the single biggest execution bottleneck in the code
        # we should be able to delete it
        # user defined equivalence
        if not onlyUser:
            (
                tmpTranslator,
                translationKeys,
                conventionDict,
            ) = detectOntology.analyzeNamingConventions(
                strippedMolecules, self.namingConventions, similarityThreshold=threshold
            )
        # user defined naming convention
        if self.userEquivalencesDict is None and hasattr(self, "userEquivalences"):
            (
                self.userEquivalencesDict,
                self.modifiedElementDictionary,
            ) = self.analyzeUserDefinedEquivalences(molecules, self.userEquivalences)
        else:
            if self.userEquivalencesDict is None:
                self.userEquivalencesDict = {}
        """
        for name in self.userEquivalencesDict:
            equivalenceTranslator[name] = self.userEquivalencesDict[name]
        """

        # add stuff to the main translator
        for element in self.userEquivalencesDict:
            if element not in tmpTranslator:
                tmpTranslator[element] = []
            tmpTranslator[element].extend(self.userEquivalencesDict[element])
        return tmpTranslator, translationKeys, conventionDict

    def processAdHocNamingConventions(
        self, reactant, product, localSpeciesDict, compartmentChangeFlag, moleculeSet
    ):
        """
        1-1 string comparison. This method will attempt to detect if there's
        a modifiation relatinship between string <reactant> and <product>

        >>> sa = SBMLAnalyzer(None,'./config/reactionDefinitions.json','./config/namingConventions.json')
        >>> sa.processAdHocNamingConventions('EGF_EGFR_2','EGF_EGFR_2_P', {}, False, ['EGF','EGFR', 'EGF_EGFR_2'])
        [[[['EGF_EGFR_2'], ['EGF_EGFR_2_P']], '_p', ('+ _', '+ p')]]
        >>> sa.processAdHocNamingConventions('A', 'A_P', {}, False,['A','A_P']) #changes neeed to be at least 3 characters long
        [[[['A'], ['A_P']], None, None]]
        >>> sa.processAdHocNamingConventions('Ras_GDP', 'Ras_GTP', {}, False,['Ras_GDP','Ras_GTP', 'Ras'])
        [[[['Ras'], ['Ras_GDP']], '_gdp', ('+ _', '+ g', '+ d', '+ p')], [[['Ras'], ['Ras_GTP']], '_gtp', ('+ _', '+ g', '+ t', '+ p')]]
        >>> sa.processAdHocNamingConventions('cRas_GDP', 'cRas_GTP', {}, False,['cRas_GDP','cRas_GTP'])
        [[[['cRas'], ['cRas_GDP']], '_gdp', ('+ _', '+ g', '+ d', '+ p')], [[['cRas'], ['cRas_GTP']], '_gtp', ('+ _', '+ g', '+ t', '+ p')]]

        """

        # strippedMolecules = [x.strip('()') for x in molecules]
        molecules = (
            [reactant, product] if len(reactant) < len(product) else [product, reactant]
        )
        similarityThreshold = 10
        if reactant == product:
            return [[[[reactant], [product]], None, None]]

        namePairs, differenceList, _ = detectOntology.defineEditDistanceMatrix(
            molecules, similarityThreshold=similarityThreshold
        )
        # print('+++',namePairs,differenceList)
        # print('---',detectOntology.defineEditDistanceMatrix2(molecules,similarityThreshold=similarityThreshold))

        # FIXME:in here we need a smarter heuristic to detect actual modifications
        # for now im just going with a simple heuristic that if the species name
        # is long enough, and the changes from a to be are all about modification
        longEnough = 3

        if len(differenceList) > 0 and (
            (len(reactant) >= longEnough and len(reactant) >= len(differenceList[0]))
            or reactant in moleculeSet
        ):
            # one is strictly a subset of the other a,a_b
            if len([x for x in differenceList[0] if "-" in x]) == 0:
                return [
                    [
                        [[reactant], [product]],
                        "".join([x[-1] for x in differenceList[0]]),
                        differenceList[0],
                    ]
                ]
            # string share a common subset but they contain mutually exclusive appendixes: a_b,a_c
            else:

                commonRoot = detectOntology.findLongestSubstring(reactant, product)

                if len(commonRoot) > longEnough or commonRoot in moleculeSet:
                    # find if we can find a commonRoot from existing molecules
                    mostSimilarRealMolecules = get_close_matches(
                        commonRoot,
                        [x for x in moleculeSet if x not in [reactant, product]],
                    )
                    for commonMolecule in mostSimilarRealMolecules:
                        if commonMolecule in reactant and commonMolecule in product:
                            commonRoot = commonMolecule
                            logMess(
                                "DEBUG:LAE003",
                                "common root {0}={1}:{2}".format(
                                    commonRoot, reactant, product
                                ),
                            )
                        # if commonMolecule == commonRoot.strip('_'):
                        #    commonRoot= commonMolecule
                        #    break
                    molecules = [commonRoot, reactant, product]
                    (
                        namePairs,
                        differenceList,
                        _,
                    ) = detectOntology.defineEditDistanceMatrix(
                        [commonRoot, reactant], similarityThreshold=10
                    )
                    (
                        namePairs2,
                        differenceList2,
                        _,
                    ) = detectOntology.defineEditDistanceMatrix(
                        [commonRoot, product], similarityThreshold=10
                    )
                    namePairs.extend(namePairs2)
                    # print(namePairs, reactant, product)
                    # XXX: this was just turning the heuristic off
                    # for element in namePairs:
                    # supposed modification is actually a pre-existing species. if that happens then refuse to proceeed
                    #    if element[1] in moleculeSet:
                    #        return [[[[reactant],[product]],None,None]]

                    differenceList.extend(differenceList2)
                    # obtain the name of the component from an anagram using the modification letters
                    validDifferences = [
                        "".join([x[-1] for x in difference])
                        for difference in differenceList
                        if "-" not in [y[0] for y in difference]
                    ]
                    validDifferences.sort()
                    # avoid trivial differences
                    if len(validDifferences) < 2 or any(
                        [x in moleculeSet for x in validDifferences]
                    ):
                        return [[[[reactant], [product]], None, None]]
                    # FIXME:here it'd be helpful to come up with a better heuristic
                    # for infered component names
                    # componentName =  ''.join([x[0:max(1,int(math.ceil(len(x)/2.0)))] for x in validDifferences])

                    # for namePair,difference in zip(namePairs,differenceList):
                    #    if len([x for x in difference if '-' in x]) == 0:
                    #        tag = ''.join([x[-1] for x in difference])
                    #        if [namePair[0],tag] not in localSpeciesDict[commonRoot][componentName]:
                    #            localSpeciesDict[namePair[0]][componentName].append([namePair[0],tag,compartmentChangeFlag])
                    #            localSpeciesDict[namePair[1]][componentName].append([namePair[0],tag,compartmentChangeFlag])

                    # namePairs,differenceList,_ = detectOntology.defineEditDistanceMatrix([commonRoot,product],
                    #
                    #                                               similarityThreshold=similarityThreshold)
                    return [
                        [
                            [[namePairs[y][0]], [namePairs[y][1]]],
                            "".join([x[-1] for x in differenceList[y]]),
                            differenceList[y],
                        ]
                        for y in range(len(differenceList))
                    ]
        return [[[[reactant], [product]], None, None]]

    def compareStrings(self, reactant, product, strippedMolecules):
        if reactant in strippedMolecules:
            if reactant in product:
                return reactant, [reactant]
                # pairedMolecules.append((reactant[idx],reactant[idx]))
                # product.remove(reactant[idx])
                # reactant.remove(reactant[idx])
            else:
                closeMatch = get_close_matches(reactant, product)
                if len(closeMatch) == 1:
                    # pairedMolecules.append((reactant[idx],closeMatch[0]))
                    # product.remove(closeMatch[0])
                    # reactant.remove(reactant[idx])
                    return (reactant, closeMatch)
                elif len(closeMatch) > 0:
                    s = difflib.SequenceMatcher()
                    s.set_seq1(reactant)
                    scoreDictionary = []
                    for match in closeMatch:
                        s.set_seq2(match)
                        scoreDictionary.append((s.ratio(), match))
                    scoreDictionary.sort(reverse=True)
                    return reactant, [closeMatch[0]]
                else:
                    return None, []
        else:

            if reactant not in product:
                closeMatch = get_close_matches(reactant, product)
                if len(closeMatch) == 1:
                    if closeMatch[0] in strippedMolecules:
                        return reactant, closeMatch
                    else:
                        closeMatchToBaseMolecules = get_close_matches(
                            closeMatch[0], strippedMolecules
                        )
                        if len(closeMatchToBaseMolecules) == 1:
                            return reactant, closeMatch
                        return None, closeMatch

                    # pairedMolecules.append((reactant[idx],closeMatch[0]))
                    # product.remove(closeMatch[0])
                    # reactant.remove(reactant[idx])
                else:
                    return None, closeMatch
                    # print('****',reactant[idx],closeMatch,difflib.get_close_matches(reactant[idx],strippedMolecules))
            else:
                mcloseMatch = get_close_matches(reactant, strippedMolecules)
                # for close in mcloseMatch:
                #    if close in [x for x in reaction[0]]:
                #        return None,[close]
                return None, [reactant]

    def growString(
        self, reactant, product, rp, pp, idx, strippedMolecules, continuityFlag
    ):
        """
        currently this is the slowest method in the system because of all those calls to difflib
        """

        idx2 = 2
        treactant = [rp]
        tproduct = pp
        pidx = product.index(pp[0])
        # print(reactant,rself.breakByActionableUnit([reactant,product],strippedMolecules))
        while idx + idx2 <= len(reactant):
            treactant2 = reactant[idx : min(len(reactant), idx + idx2)]
            # if treactant2 != tproduct2:
            if treactant2[-1] in strippedMolecules and continuityFlag:
                break
            else:
                if len(reactant) > idx + idx2:
                    tailDifferences = get_close_matches(
                        treactant2[-1], strippedMolecules
                    )
                    if len(tailDifferences) > 0:

                        tdr = max(
                            [0]
                            + [
                                sequenceMatcher("_".join(treactant2), x)
                                for x in tailDifferences
                            ]
                        )
                        hdr = max(
                            [0]
                            + [
                                sequenceMatcher(
                                    "_".join(reactant[idx + idx2 - 1 : idx + idx2 + 1]),
                                    x,
                                )
                                for x in tailDifferences
                            ]
                        )
                        if tdr > hdr and tdr > 0.8:
                            treactant = treactant2
                    else:
                        tailDifferences = get_close_matches(
                            "_".join(treactant2), strippedMolecules
                        )
                        headDifferences = get_close_matches(
                            "_".join(reactant[idx + idx2 - 1 : idx + idx2 + 1]),
                            strippedMolecules,
                        )
                        if len(tailDifferences) == 0:
                            break
                        elif len(headDifferences) == 0:
                            treactant = treactant2
                        break
                elif len(reactant) == idx + idx2:
                    tailDifferences = get_close_matches(
                        "_".join(treactant2), strippedMolecules
                    )
                    if len(tailDifferences) > 0:

                        tdr = max(
                            [0]
                            + [
                                sequenceMatcher("_".join(treactant2), x)
                                for x in tailDifferences
                            ]
                        )
                        if tdr > 0.8:
                            treactant = treactant2
                        else:
                            break
                    else:
                        break
                else:
                    treactant = treactant2
            break
            idx2 += 1

        idx2 = 2
        while pidx + idx2 <= len(product):
            tproduct2 = product[pidx : min(len(product), pidx + idx2)]
            if tproduct2[-1] in strippedMolecules and continuityFlag:
                break

            else:
                if len(product) > pidx + idx2:
                    tailDifferences = get_close_matches(
                        tproduct2[-1], strippedMolecules
                    )
                    if len(tailDifferences) > 0:
                        tdr = max(
                            [0]
                            + [
                                sequenceMatcher("_".join(tproduct2), x)
                                for x in tailDifferences
                            ]
                        )
                        hdr = max(
                            [0]
                            + [
                                sequenceMatcher(
                                    "_".join(
                                        product[pidx + idx2 - 1 : pidx + idx2 + 1]
                                    ),
                                    x,
                                )
                                for x in tailDifferences
                            ]
                        )
                        if tdr > hdr and tdr > 0.8:
                            tproduct = tproduct2
                    else:
                        tailDifferences = get_close_matches(
                            "_".join(tproduct2), strippedMolecules, cutoff=0.8
                        )
                        headDifferences = get_close_matches(
                            "_".join(product[pidx + idx2 - 1 : pidx + idx2 + 1]),
                            strippedMolecules,
                            cutoff=0.8,
                        )
                        if len(tailDifferences) == 0:
                            break
                        elif (
                            len(headDifferences) == 0
                            or "_".join(tproduct2) in tailDifferences
                        ):
                            tproduct = tproduct2

                elif len(product) == pidx + idx2:
                    tailDifferences = get_close_matches(
                        "_".join(tproduct2), strippedMolecules
                    )
                    if len(tailDifferences) > 0:

                        tdr = max(
                            [0]
                            + [
                                sequenceMatcher("_".join(tproduct2), x)
                                for x in tailDifferences
                            ]
                        )
                        if tdr > 0.8:
                            tproduct = tproduct2
                        else:
                            break
                    else:
                        break

                else:
                    tproduct = tproduct2
            break
            # if '_'.join(tproduct2) in strippedMolecules and '_'.join(treactant2) in strippedMolecules:
            #    tproduct = tproduct2
            #    treactant = treactant2
            # else:

            idx2 += 1
        return treactant, tproduct

    def approximateMatching2(
        self, reactantString, productString, strippedMolecules, differenceParameter
    ):
        """
        The meat of the naming convention matching between reactant and product is done here
        tl;dr naming conventions are hard
        """

        # reactantString = [x.split('_') for x in reaction[0]]
        # reactantString = [[y for y in x if y!=''] for x in reactantString]
        # productString = [x.split('_') for x in reaction[1]]
        # productString = [[y for y in x if y!=''] for x in productString]

        pairedMolecules = [[] for _ in range(len(productString))]
        pairedMolecules2 = [[] for _ in range(len(reactantString))]

        for stoch, reactant in enumerate(reactantString):
            idx = -1
            while idx + 1 < len(reactant):
                idx += 1
                for stoch2, product in enumerate(productString):
                    # print(idx2,product in enumerate(element3):)
                    rp, pp = self.compareStrings(
                        reactant[idx], product, strippedMolecules
                    )
                    if rp and rp != pp[0]:
                        pairedMolecules[stoch2].append((rp, pp[0]))
                        pairedMolecules2[stoch].append((pp[0], rp))
                        product.remove(pp[0])
                        reactant.remove(rp)
                        # product.remove(pp)
                        # reactant.remove(rp)
                        idx = -1
                        break
                    elif rp:
                        treactant, tproduct = self.growString(
                            reactant,
                            product,
                            rp,
                            pp,
                            idx,
                            strippedMolecules,
                            continuityFlag=True,
                        )
                        if "_".join(treactant) in strippedMolecules:
                            finalReactant = "_".join(treactant)
                        else:

                            reactantMatches = get_close_matches(
                                "_".join(treactant), strippedMolecules
                            )
                            if len(reactantMatches) > 0:
                                reactantScore = [
                                    sequenceMatcher(
                                        "".join(treactant), x.replace("_", "")
                                    )
                                    for x in reactantMatches
                                ]
                                finalReactant = reactantMatches[
                                    reactantScore.index(max(reactantScore))
                                ]
                            else:
                                finalReactant = "_".join(treactant)

                        if "_".join(tproduct) in strippedMolecules:

                            finalProduct = "_".join(tproduct)
                        else:
                            productMatches = get_close_matches(
                                "_".join(tproduct), strippedMolecules
                            )
                            if len(productMatches) > 0:
                                productScore = [
                                    sequenceMatcher(
                                        "".join(tproduct), x.replace("_", "")
                                    )
                                    for x in productMatches
                                ]
                                finalProduct = productMatches[
                                    productScore.index(max(productScore))
                                ]
                            else:
                                finalProduct = "_".join(tproduct)

                        pairedMolecules[stoch2].append((finalReactant, finalProduct))
                        pairedMolecules2[stoch].append((finalProduct, finalReactant))

                        for x in treactant:
                            reactant.remove(x)
                        for x in tproduct:
                            product.remove(x)
                        idx = -1
                        break
                    else:
                        flag = False
                        if pp not in [[], None]:
                            # if reactant[idx] == pp[0]:
                            treactant, tproduct = self.growString(
                                reactant,
                                product,
                                reactant[idx],
                                pp,
                                idx,
                                strippedMolecules,
                                continuityFlag=False,
                            )
                            # FIXME: this comparison is pretty nonsensical. treactant and tproduct are not
                            # guaranteed to be in teh right order. why are we comparing them both at the same time
                            if (
                                len(treactant) > 1
                                and "_".join(treactant) in strippedMolecules
                            ) or (
                                len(tproduct) > 1
                                and "_".join(tproduct) in strippedMolecules
                            ):
                                pairedMolecules[stoch2].append(
                                    ("_".join(treactant), "_".join(tproduct))
                                )
                                pairedMolecules2[stoch].append(
                                    ("_".join(tproduct), "_".join(treactant))
                                )
                                for x in treactant:
                                    reactant.remove(x)
                                for x in tproduct:
                                    product.remove(x)
                                idx = -1
                                break
                            else:
                                rclose = get_close_matches(
                                    "_".join(treactant), strippedMolecules
                                )
                                pclose = get_close_matches(
                                    "_".join(tproduct), strippedMolecules
                                )
                                rclose2 = [x.split("_") for x in rclose]
                                rclose2 = [
                                    "_".join([y for y in x if y != ""]) for x in rclose2
                                ]
                                pclose2 = [x.split("_") for x in pclose]
                                pclose2 = [
                                    "_".join([y for y in x if y != ""]) for x in pclose2
                                ]
                                trueReactant = None
                                trueProduct = None
                                try:
                                    trueReactant = rclose[
                                        rclose2.index("_".join(treactant))
                                    ]
                                    trueProduct = pclose[
                                        pclose2.index("_".join(tproduct))
                                    ]
                                except:
                                    pass
                                if trueReactant and trueProduct:
                                    pairedMolecules[stoch2].append(
                                        (trueReactant, trueProduct)
                                    )
                                    pairedMolecules2[stoch].append(
                                        (trueProduct, trueReactant)
                                    )
                                    for x in treactant:
                                        reactant.remove(x)
                                    for x in tproduct:
                                        product.remove(x)
                                    idx = -1
                                    break

        if (
            sum(len(x) for x in reactantString + productString) > 0
            and self.conservationOfMass
        ):
            return None, None
        else:
            return pairedMolecules, pairedMolecules2

    def approximateMatching(self, ruleList, differenceParameter=[]):
        def curateString(
            element,
            differences,
            symbolList=["#", "&", ";", "@", "!", "?"],
            equivalenceDict={},
        ):
            """
            remove compound differencese (>2 characters) and instead represent them with symbols
            returns transformed string,an equivalence dictionary and unused symbols
            """
            tmp = element
            for difference in differences:
                if difference in element:
                    if difference.startswith("_"):
                        if difference not in equivalenceDict:
                            symbol = symbolList.pop()
                            equivalenceDict[difference] = symbol
                        else:
                            symbol = equivalenceDict[difference]
                        tmp = re.sub(
                            r"{0}(_|$)".format(difference), r"{0}\1".format(symbol), tmp
                        )
                    elif difference.endswith("_"):
                        if difference not in equivalenceDict:
                            symbol = symbolList.pop()
                            equivalenceDict[difference] = symbol
                        else:
                            symbol = equivalenceDict[difference]

                        tmp = re.sub(
                            r"(_|^){0}".format(difference), r"{0}\1".format(symbol), tmp
                        )
            return tmp, symbolList, equivalenceDict

        """
        given a transformation of the kind a+ b -> ~a_~b, where ~a and ~b are some
        slightly modified version of a and b, this function will return a list of 
        lexical changes that a and b must undergo to become ~a and ~b.
        """
        flag = True
        if len(ruleList[1]) == 1 and ruleList[1] != "0":
            differences = deepcopy(differenceParameter)
            tmpRuleList = deepcopy(ruleList)

            while flag:
                flag = False
                sym = ["#", "&", ";", "@", "!", "?"]
                dic = {}
                for idx, _ in enumerate(tmpRuleList[0]):
                    tmpRuleList[0][idx], sym, dic = curateString(
                        ruleList[0][idx], differences, sym, dic
                    )

                tmpRuleList[1][0], sym, dic = curateString(
                    ruleList[1][0], differences, sym, dic
                )
                permutations = [x for x in itertools.permutations(ruleList[0])]
                tpermutations = [x for x in itertools.permutations(tmpRuleList[0])]
                score = [
                    difflib.SequenceMatcher(None, "_".join(x), ruleList[1][0]).ratio()
                    for x in permutations
                ]
                maxindex = score.index(max(score))
                ruleList[0] = list(permutations[maxindex])
                tmpRuleList[0] = list(tpermutations[maxindex])

                sym = [dic[x] for x in dic]
                sym.extend(differences)
                sym = [x for x in sym if "_" not in x]
                simplifiedDifference = difflib.SequenceMatcher(
                    lambda x: x in sym, "-".join(tmpRuleList[0]), tmpRuleList[1][0]
                )

                matches = simplifiedDifference.get_matching_blocks()
                if len(matches) != len(ruleList[0]) + 1:
                    return [[], []], [[], []]

                productPartitions = []
                for idx, match in enumerate(matches):
                    if matches[idx][2] != 0:
                        productPartitions.append(
                            tmpRuleList[1][0][
                                matches[idx][1] : matches[idx][1] + matches[idx][2]
                            ]
                        )
                reactantPartitions = tmpRuleList[0]

                # Don't count trailing underscores as part of the species name
                for idx, _ in enumerate(reactantPartitions):
                    reactantPartitions[idx] = reactantPartitions[idx].strip("_")
                for idx, _ in enumerate(productPartitions):
                    productPartitions[idx] = productPartitions[idx].strip("_")

                # greedymatching

                acc = 0
                # FIXME:its not properly copying all the string
                for idx in range(0, len(matches) - 1):
                    while (
                        matches[idx][2] + acc < len(tmpRuleList[1][0])
                        and tmpRuleList[1][0][matches[idx][2] + acc] in sym
                    ):
                        productPartitions[idx] += tmpRuleList[1][0][
                            matches[idx][2] + acc
                        ]
                        acc += 1

                # idx = 0
                # while(tmpString[matches[0][2]+ idx]  in sym):
                #    reactantfirstHalf += tmpString[matches[0][2] + idx]
                #    idx += 1

                for element in dic:
                    for idx in range(len(productPartitions)):
                        productPartitions[idx] = productPartitions[idx].replace(
                            dic[element], element
                        )
                        reactantPartitions[idx] = reactantPartitions[idx].replace(
                            dic[element], element
                        )

                zippedPartitions = list(zip(reactantPartitions, productPartitions))
                zippedPartitions = [sorted(x, key=len) for x in zippedPartitions]
                bdifferences = [
                    [z for z in y if "+ " in z or "- " in z]
                    for y in [difflib.ndiff(*x) for x in zippedPartitions]
                ]

                processedDifferences = [
                    "".join([y.strip("+ ") for y in x]) for x in bdifferences
                ]

                for idx, processedDifference in enumerate(processedDifferences):
                    if (
                        processedDifference not in differences
                        and "- " not in processedDifference
                        and bdifferences[idx] != []
                    ):
                        flag = True
                        differences.append(processedDifference)

        else:
            # TODO: dea with reactions of the kindd a+b ->  c + d
            return [[], []], [[], []]
        return bdifferences, zippedPartitions

    def getReactionClassification(
        self,
        reactionDefinition,
        rules,
        equivalenceTranslator,
        indirectEquivalenceTranslator,
        translationKeys=[],
    ):
        """
        *reactionDefinition* is a list of conditions that must be met for a reaction
        to be classified a certain way
        *rules* is the list of reactions
        *equivalenceTranslator* is a dictinary containing all complexes that have been
        determined to be the same through naming conventions
        This method will go through the list of rules and the list of rule definitions
        and tell us which rules it can classify according to the rule definitions list
        provided
        """
        ruleDictionary = self.species2Rules(rules)
        # determines a reaction's reactionStructure aka stoichoimetry
        ruleComplianceMatrix = np.zeros(
            (len(rules), len(reactionDefinition["reactions"]))
        )
        for (idx, rule) in enumerate(rules):
            reaction2 = rule  # list(parseReactions(rule))
            ruleComplianceMatrix[idx] = self.identifyReactions2(
                reaction2, reactionDefinition
            )
        # initialize the tupleComplianceMatrix array with the same keys as ruleDictionary
        # the tuple complianceMatrix is basically there to make sure we evaluate
        # bidirectional reactions as one reaction
        tupleComplianceMatrix = {
            key: np.zeros((len(reactionDefinition["reactions"])))
            for key in ruleDictionary
        }
        # check which reaction conditions each tuple satisfies
        for element in ruleDictionary:
            for rule in ruleDictionary[element]:
                tupleComplianceMatrix[element] += ruleComplianceMatrix[rule]

        # now we will check for the nameConventionMatrix (same thing as before but for naming conventions)
        tupleNameComplianceMatrix = {
            key: {key2: 0 for key2 in equivalenceTranslator} for key in ruleDictionary
        }
        for rule in ruleDictionary:
            for namingConvention in equivalenceTranslator:
                for equivalence in equivalenceTranslator[namingConvention]:
                    if all(element in rule for element in equivalence):
                        tupleNameComplianceMatrix[rule][namingConvention] += 1
                        break
                for equivalence in indirectEquivalenceTranslator[namingConvention]:
                    if all(element in rule for element in equivalence[0]):
                        tupleNameComplianceMatrix[rule][namingConvention] += 1
                        break
                        # we can have more than one
                    # elif appro
        # check if the reaction conditions each tuple satisfies are enough to get classified
        # as an specific named reaction type
        tupleDefinitionMatrix = {
            key: np.zeros((len(reactionDefinition["definitions"])))
            for key in ruleDictionary
        }
        for key, element in list(tupleComplianceMatrix.items()):
            for idx, member in enumerate(reactionDefinition["definitions"]):
                for alternative in member:
                    if "r" in alternative:
                        tupleDefinitionMatrix[key][idx] += np.all(
                            [element[reaction] for reaction in alternative["r"]]
                        )
                    if (
                        "n" in alternative
                        and reactionDefinition["reactionsNames"][idx]
                        in equivalenceTranslator
                    ):
                        tupleDefinitionMatrix[key][idx] += np.all(
                            [
                                tupleNameComplianceMatrix[key][
                                    reactionDefinition["reactionsNames"][idx]
                                ]
                            ]
                        )
        # cotains which rules are equal to reactions defined in reactionDefinitions['definitions']
        # use the per tuple classification to obtain a per reaction classification
        ruleDefinitionMatrix = np.zeros(
            (len(rules), len(reactionDefinition["definitions"]))
        )
        for key, element in list(ruleDictionary.items()):
            for rule in element:
                ruleDefinitionMatrix[rule] = self.checkCompliance(
                    ruleComplianceMatrix[rule],
                    tupleDefinitionMatrix[key],
                    reactionDefinition["definitions"],
                )
        # use reactionDefinitions reactionNames field to actually tell us what reaction
        # type each reaction is
        results = []
        for idx, element in enumerate(ruleDefinitionMatrix):
            nonZero = np.nonzero(element)[0]
            if len(nonZero) == 0:
                results.append("None")
            # todo: need to do something if it matches more than one reaction
            else:
                classifications = [
                    reactionDefinition["reactionsNames"][x] for x in nonZero
                ]
                # FIXME: we should be able to support more than one transformation
                results.append(classifications[0])
        return results

    def setConfigurationFile(self, configurationFile):
        self.configurationFile = configurationFile

    def getReactionProperties(self):
        """
        if we are using a naming convention definition in the json file
        this method will return the component and state names that this
        reaction uses
        """

        # TODO: once we transition completely to a naming convention delete
        # this ----
        reactionTypeProperties = {}
        reactionDefinition = self.loadConfigFiles(self.configurationFile)
        if self.speciesEquivalences != None:
            self.userEquivalences = self.loadConfigFiles(self.speciesEquivalences)[
                "reactionDefinition"
            ]
        for reactionType, properties in zip(
            reactionDefinition["reactionsNames"], reactionDefinition["definitions"]
        ):
            # if its a reaction defined by its naming convention
            # xxxxxxxxxxxxxxxxxxx
            for alternative in properties:
                if "n" in list(alternative.keys()):
                    try:
                        site = reactionDefinition["reactionSite"][alternative["rsi"]]
                        state = reactionDefinition["reactionState"][alternative["rst"]]
                    except:
                        site = reactionType
                        state = reactionType[0]
                    reactionTypeProperties[reactionType] = [site, state]
        # TODO: end of delete
        reactionDefinition = self.namingConventions
        for idx, reactionType in enumerate(reactionDefinition["modificationList"]):
            site = reactionDefinition["reactionSite"][
                reactionDefinition["definitions"][idx]["rsi"]
            ]
            state = reactionDefinition["reactionState"][
                reactionDefinition["definitions"][idx]["rst"]
            ]
            reactionTypeProperties[reactionType] = [site, state]
        return reactionTypeProperties

    def processFuzzyReaction(
        self, reaction, translationKeys, conventionDict, indirectEquivalenceTranslator
    ):
        differences, pairedChemicals = self.approximateMatching(
            reaction, translationKeys
        )
        # matching,matching2 = self.approximateMatching2(reaction,strippedMolecules,
        #                                               translationKeys)

        d1, d2 = differences[0], differences[1]
        firstMatch, secondMatch = pairedChemicals[0], pairedChemicals[1]
        matches = [firstMatch, secondMatch]
        for index, element in enumerate([d1, d2]):
            idx1 = 0
            idx2 = 1
            while idx2 <= len(element):
                if (element[idx1],) in list(conventionDict.keys()):
                    pattern = conventionDict[(element[idx1],)]
                    indirectEquivalenceTranslator[pattern].append(
                        [
                            [reaction[0][index], reaction[1][0]],
                            reaction[0],
                            matches[index],
                            reaction[1],
                        ]
                    )
                elif (element[idx1].replace("-", "+"),) in list(conventionDict.keys()):
                    matches[index].reverse()
                    transformedPattern = conventionDict[
                        (element[idx1].replace("-", "+"),)
                    ]
                    indirectEquivalenceTranslator[transformedPattern].append(
                        [
                            [reaction[1][0], reaction[0][index]],
                            reaction[0],
                            matches[index],
                            reaction[1],
                        ]
                    )
                elif idx2 < len(element):
                    if tuple([element[idx1], element[idx2]]) in list(
                        conventionDict.keys()
                    ):
                        pattern = conventionDict[tuple([element[idx1], element[idx2]])]
                        indirectEquivalenceTranslator[pattern].append(
                            [
                                [reaction[0][index], reaction[1][0]],
                                reaction[0],
                                matches[index],
                                reaction[1],
                            ]
                        )
                        idx1 += 1
                        idx2 += 1
                    elif "-" in element[idx1] and "-" in element[idx2]:
                        if (
                            tuple(
                                [
                                    element[idx1].replace("-", "+"),
                                    element[idx2].replace("-", "+"),
                                ]
                            )
                            in list(conventionDict.keys())
                        ):
                            matches[index].reverse()
                            transformedPattern = conventionDict[
                                tuple(
                                    [
                                        element[idx1].replace("-", "+"),
                                        element[idx2].replace("-", "+"),
                                    ]
                                )
                            ]
                            indirectEquivalenceTranslator[transformedPattern].append(
                                [
                                    [reaction[1][0], reaction[0][index]],
                                    reaction[0],
                                    matches[index],
                                    reaction[1],
                                ]
                            )
                            idx1 += 1
                            idx2 += 1

                idx1 += 1
                idx2 += 1

    def removeExactMatches(self, reactantList, productList):
        """
        goes through the list of lists reactantList and productList and removes the intersection
        """
        reactantFlat = Counter([y for x in reactantList for y in x])
        productFlat = Counter([y for x in productList for y in x])
        intersection = reactantFlat & productFlat
        intersection2 = deepcopy(intersection)
        newReactant = []
        newProduct = []
        for chemical in reactantList:
            tmp = []
            for element in chemical:
                if intersection[element] > 0:
                    intersection[element] -= 1
                else:
                    tmp.append(element)
            newReactant.append(tmp)
        for chemical in productList:
            tmp = []
            for element in chemical:
                if intersection2[element] > 0:
                    intersection2[element] -= 1
                else:
                    tmp.append(element)
            newProduct.append(tmp)

        return newReactant, newProduct

    def findBiggestActionable(self, chemicalList, chemicalCandidatesList):
        actionableList = []
        for chemical, chemicalCandidates in zip(chemicalList, chemicalCandidatesList):
            if len(chemicalCandidates) == 0:
                return None
            if len(chemicalCandidates) == 1:
                actionableList.append([chemical])
                continue
            # find all combinations
            scoreDict = []
            result = 0
            try:
                for i in range(1, len(chemicalCandidates) + 1):
                    combinations = list(itertools.permutations(chemicalCandidates, i))
                    for x in combinations:

                        score = difflib.SequenceMatcher(
                            None, "_".join(x), chemical
                        ).quick_ratio()
                        if score == 1:
                            result = x
                            raise IOError
                        elif score > 0:
                            scoreDict.append([x, score])
            except IOError:
                scoreDict = [[result, 1.0]]
            scoreDict.sort(key=lambda x: [x[1], -len(x[0])], reverse=True)
            if len(scoreDict) > 0:
                actionableList.append(list(scoreDict[0][0]))
            else:
                print(actionableList)
                raise Exception
        return actionableList

    def breakByActionableUnit(self, reaction, strippedMolecules):
        # find valid actionable units from the list of molecules in the system
        validCandidatesReactants = [
            [y for y in strippedMolecules if y in x] for x in reaction[0]
        ]
        validCandidatesProducts = [
            [y for y in strippedMolecules if y in x] for x in reaction[1]
        ]

        # find the subset of intersection parts between reactants and products
        intermediateVector = [
            list(
                filter(
                    lambda x: any(
                        [
                            len(
                                [
                                    z
                                    for z in difflib.ndiff(x, y)
                                    if "+" in z[0] or "-" in z[0]
                                ]
                            )
                            <= 3
                            for z in validCandidatesProducts
                            for y in z
                        ]
                    ),
                    sublist,
                )
            )
            for sublist in validCandidatesReactants
        ]
        intermediateVector = [
            list(
                filter(
                    lambda x: any(
                        [
                            len(
                                [
                                    z
                                    for z in difflib.ndiff(x, y)
                                    if "+" in z[0] or "-" in z[0]
                                ]
                            )
                            <= 3
                            for z in intermediateVector
                            for y in z
                        ]
                    ),
                    sublist,
                )
            )
            for sublist in validCandidatesProducts
        ]

        tmpReactant = [
            [
                list(
                    filter(
                        lambda y: len([x for x in intermediateVector[0] if y in x])
                        == 1,
                        reactant,
                    )
                )
            ]
            for reactant in validCandidatesReactants
        ]
        tmpProduct = [
            [
                list(
                    filter(
                        lambda y: len([x for x in intermediateVector[0] if y in x])
                        == 1,
                        reactant,
                    )
                )
            ]
            for reactant in validCandidatesProducts
        ]

        # print(validCandidatesReactants,validCandidatesProducts,intermediateVector)
        # print('......',reaction)
        # print('\t......',validCandidatesReactants,validCandidatesProducts)

        # find biggest subset of actionable units

        reactantList = self.findBiggestActionable(reaction[0], validCandidatesReactants)
        productList = self.findBiggestActionable(reaction[1], validCandidatesProducts)

        # print('\t\t+++++',reactantList,productList)
        return reactantList, productList

    def testAgainstExistingConventions(self, fuzzyKey, modificationList, threshold=4):
        @memoize
        def testAgainstExistingConventionsHelper(fuzzyKey, modificationList, threshold):
            if not fuzzyKey:
                return None
            for i in range(1, threshold):
                combinations = itertools.permutations(modificationList, i)

                validKeys = list(
                    filter(
                        lambda x: ("".join(x)).upper() == fuzzyKey.upper(), combinations
                    )
                )

                if validKeys:
                    return validKeys
            return None

        return testAgainstExistingConventionsHelper(
            fuzzyKey, modificationList, threshold
        )

    def classifyReactions(self, reactions, molecules, externalDependencyGraph={}):
        """
        classifies a group of reaction according to the information in the json
        config file

        FIXME:classifiyReactions function is currently the biggest bottleneck in atomizer, taking up
        to 80% of the time without counting pathwaycommons querying.
        """

        def createArtificialNamingConvention(reaction, fuzzyKey, fuzzyDifference):
            """
            Does the actual data-structure filling if
            a 1-1 reaction shows sign of modification. Returns True if
            a change was performed
            """
            # fuzzyKey,fuzzyDifference = self.processAdHocNamingConventions(reaction[0][0],reaction[1][0],localSpeciesDict,compartmentChangeFlag)
            if fuzzyKey and fuzzyKey.strip("_").lower() not in [
                x.lower() for x in strippedMolecules
            ]:
                # if our state isnt yet on the dependency graph preliminary data structures
                if "{0}".format(fuzzyKey) not in equivalenceTranslator:
                    # print('---','{0}'.format(fuzzyKey),equivalenceTranslator.keys())
                    # check if there is a combination of existing keys that deals with this modification without the need of creation a new one
                    if self.testAgainstExistingConventions(
                        fuzzyKey, self.namingConventions["modificationList"]
                    ):
                        logMess(
                            "INFO:LAE005",
                            "added relationship through existing convention in reaction {0}".format(
                                str(reaction)
                            ),
                        )
                        if "{0}".format(fuzzyKey) not in equivalenceTranslator:
                            equivalenceTranslator["{0}".format(fuzzyKey)] = []
                        if "{0}".format(fuzzyKey) not in indirectEquivalenceTranslator:
                            indirectEquivalenceTranslator["{0}".format(fuzzyKey)] = []
                        if (
                            tuple(sorted([x[0] for x in reaction], key=len))
                            not in equivalenceTranslator["{0}".format(fuzzyKey)]
                        ):
                            equivalenceTranslator["{0}".format(fuzzyKey)].append(
                                tuple(sorted([x[0] for x in reaction], key=len))
                            )
                        return
                    logMess(
                        "INFO:LAE004",
                        "{0}:{1}:added induced naming convention".format(
                            reaction[0][0], reaction[1][0]
                        ),
                    )
                    equivalenceTranslator["{0}".format(fuzzyKey)] = []
                    if fuzzyKey == "0":
                        tmpState = "ON"
                    else:
                        tmpState = fuzzyKey.upper()

                    adhocLabelDictionary["{0}".format(fuzzyKey)] = [
                        "{0}".format(fuzzyKey),
                        tmpState,
                    ]
                    # fill main naming convention data structure
                    self.namingConventions["modificationList"].append(
                        "{0}".format(fuzzyKey)
                    )
                    self.namingConventions["reactionState"].append(tmpState)
                    self.namingConventions["reactionSite"].append(
                        "{0}".format(fuzzyKey)
                    )
                    self.namingConventions["patterns"][fuzzyDifference] = "{0}".format(
                        fuzzyKey
                    )
                    self.namingConventions["definitions"].append(
                        {
                            "rst": len(self.namingConventions["reactionState"]) - 1,
                            "rsi": len(self.namingConventions["reactionSite"]) - 1,
                        }
                    )
                    if fuzzyKey not in translationKeys:
                        translationKeys.append(fuzzyKey)
                # if this same definition doesnt already exist. this is to avoid cycles
                if (
                    tuple(sorted([x[0] for x in reaction], key=len))
                    not in equivalenceTranslator["{0}".format(fuzzyKey)]
                ):
                    equivalenceTranslator["{0}".format(fuzzyKey)].append(
                        tuple(sorted([x[0] for x in reaction], key=len))
                    )
                    newTranslationKeys.append(fuzzyKey)
                conventionDict[fuzzyDifference] = "{0}".format(fuzzyKey)
                if "{0}".format(fuzzyKey) not in indirectEquivalenceTranslator:
                    indirectEquivalenceTranslator["{0}".format(fuzzyKey)] = []
                return True
            return False

        # load the json config file
        reactionDefinition = self.loadConfigFiles(self.configurationFile)
        rawReactions = []

        for x in reactions:
            tmp = parseReactions(x)
            if tmp:
                rawReactions.append(tmp)

        # rawReactions = [parseReactions(x) for x in reactions if parseReactions(x)]
        strippedMolecules = [x.strip("()") for x in molecules]
        reactionnetworkelements = set([z for x in rawReactions for y in x for z in y])
        # only keep those molecuels that appear in the reaction network
        strippedMolecules = [
            x for x in strippedMolecules if x in reactionnetworkelements
        ]

        # load user defined complexes
        if self.speciesEquivalences != None:
            self.userEquivalences = self.loadConfigFiles(self.speciesEquivalences)[
                "reactionDefinition"
            ]
        # determines if two molecules have a relationship according to the naming convention section
        # equivalenceTranslator is a dictionary of actual modifications
        # example {'Phosporylation':[['A','A_p'],['B','B_p']]}

        # process straightforward naming conventions
        # XXX: we should take this function out of processNamingConventions2 and all process that calls it
        (
            tmpTranslator,
            translationKeys,
            conventionDict,
        ) = detectOntology.analyzeNamingConventions(
            strippedMolecules, self.userNamingConventions, similarityThreshold=10
        )
        userEquivalenceTranslator, _, _ = self.processNamingConventions2(
            strippedMolecules, onlyUser=True
        )
        for element in tmpTranslator:
            if element in userEquivalenceTranslator:
                userEquivalenceTranslator[element].extend(tmpTranslator[element])
            else:
                userEquivalenceTranslator[element] = tmpTranslator[element]
        equivalenceTranslator = copy(userEquivalenceTranslator)

        newTranslationKeys = []
        adhocLabelDictionary = {}

        # lists of plain reactions

        # process fuzzy naming conventions based on reaction information
        indirectEquivalenceTranslator = {x: [] for x in equivalenceTranslator}
        localSpeciesDict = defaultdict(lambda: defaultdict(list))

        trueBindingReactions = []

        # the lexical dependencyGraph merely applies lexical analysis to detect which components in the left hand size
        # matches to different ones in the right hand size of a given reaction
        lexicalDependencyGraph = defaultdict(list)
        strippedMolecules = [x.strip("()") for x in molecules]

        # only keep those molecuels that appear in the reaction network
        strippedMolecules = [
            x for x in strippedMolecules if x in reactionnetworkelements
        ]

        for idx, reaction in enumerate(rawReactions):
            flagstar = False
            if (
                len(reaction[0]) == 1
                and len(reaction[1]) == 1
                and len(reaction[0][0]) > len(reaction[1][0])
            ):
                # unmodification/relaxatopn
                flagstar = True
                reaction = [reaction[1], reaction[0]]

            # should we reuse information obtained from other methods?
            # FIXME: instead of doing a simple split by '_' we should be comparing against the molecules in stripped molecules and split by smallest actionable units.
            if externalDependencyGraph == {}:
                # print('-----',reaction)
                # reactantString, productString = self.breakByActionableUnit(reaction, strippedMolecules)
                # print('...',reaction, reactantString, productString)
                # if not reactantString or not productString:
                reactantString = [x.split("_") for x in reaction[0]]
                reactantString = [[y for y in x if y != ""] for x in reactantString]
                productString = [x.split("_") for x in reaction[1]]
                productString = [[y for y in x if y != ""] for x in productString]

            else:

                reactantString = []
                productString = []
                # check how the reactants are composed and add it to the list
                for element in reaction[0]:
                    if (
                        element not in externalDependencyGraph
                        or externalDependencyGraph[element] == []
                    ):
                        reactantString.append([element])
                    else:
                        reactantString.append(
                            deepcopy(externalDependencyGraph[element][0])
                        )

                # same for products
                for element in reaction[1]:
                    if (
                        element not in externalDependencyGraph
                        or externalDependencyGraph[element] == []
                    ):
                        productString.append([element])
                    else:
                        productString.append(
                            deepcopy(externalDependencyGraph[element][0])
                        )

                # remove those chemicals that match exactly on both sides since those are not interesting.
                # and unlike lexical pattern matching we are not going to go around trying to increase string size
                reactantString, productString = self.removeExactMatches(
                    reactantString, productString
                )

            if [0] in reactantString or [0] in productString:
                continue
            matching, matching2 = self.approximateMatching2(
                reactantString, productString, strippedMolecules, translationKeys
            )
            # print(reaction, matching)
            # if matching and flagstar:
            #    logMess('DEBUG:Atomization', 'inverting order of {0} for lexical analysis'.format([reaction[1], reaction[0]]))

            flag = True

            if matching:
                for reactant, matches in zip(reaction[1], matching):
                    for match in matches:
                        pair = list(match)
                        pair.sort(key=len)
                        fuzzyList = self.processAdHocNamingConventions(
                            pair[0], pair[1], localSpeciesDict, False, strippedMolecules
                        )
                        for fuzzyReaction, fuzzyKey, fuzzyDifference in fuzzyList:
                            if (
                                fuzzyKey == None
                                and fuzzyReaction[0] != fuzzyReaction[1]
                            ):
                                flag = False
                                # logMess('Warning:ATOMIZATION','We could not  a meaningful \
                                # mapping in {0} when lexically analyzing {1}.'.format(pair,reactant))

                            createArtificialNamingConvention(
                                fuzzyReaction, fuzzyKey, fuzzyDifference
                            )
                    if (
                        flag
                        and sorted([x[1] for x in matches])
                        not in lexicalDependencyGraph[reactant]
                    ):
                        # dont introduce cyclical dependencies
                        if all([x[1] != reactant for x in matches]):
                            lexicalDependencyGraph[reactant].append(
                                sorted([x[1] for x in matches])
                            )
                            for x in matches:
                                # TODO(Oct14): it would be better to try to map this to an
                                # existing molecule instead of trying to create a new one
                                if x[1] not in strippedMolecules:
                                    if len(x[1]) > len(x[0]):
                                        lexicalDependencyGraph[x[1]] = [[x[0]]]
                                    else:
                                        lexicalDependencyGraph[x[0]] = [[x[1]]]
                                        lexicalDependencyGraph[x[1]] = []
        translationKeys.extend(newTranslationKeys)
        for species in localSpeciesDict:
            speciesName = localSpeciesDict[species][
                list(localSpeciesDict[species].keys())[0]
            ][0][0]
            definition = [species]
            sdefinition = [speciesName]
            for component in localSpeciesDict[species]:
                cdefinition = []
                states = [
                    ["s", state[1]] for state in localSpeciesDict[species][component]
                ]
                for state in states:
                    cdefinition.extend(state)
                cdefinition = [component, cdefinition]
                sdefinition.extend(cdefinition)
            definition.append([sdefinition])
            self.lexicalSpecies.append(definition)
            # definition = [commonRoot,[[commonRoot,componentName,["s",tag]]]]

        reactionClassification = self.getReactionClassification(
            reactionDefinition,
            rawReactions,
            equivalenceTranslator,
            indirectEquivalenceTranslator,
            translationKeys,
        )
        for element in trueBindingReactions:
            reactionClassification[element] = "Binding"
        listOfEquivalences = []
        for element in equivalenceTranslator:
            listOfEquivalences.extend(equivalenceTranslator[element])
        return (
            reactionClassification,
            listOfEquivalences,
            equivalenceTranslator,
            indirectEquivalenceTranslator,
            adhocLabelDictionary,
            lexicalDependencyGraph,
            userEquivalenceTranslator,
        )

    def processAnnotations(self, molecules, annotations):
        processedAnnotations = []
        for element in annotations:
            if len(annotations[element]) > 1:
                pro = [
                    list(x)
                    for x in itertools.combinations(
                        [y for y in annotations[element]], 2
                    )
                ]
                processedAnnotations.extend(pro)

        return {-1: processedAnnotations}

    def classifyReactionsWithAnnotations(
        self, reactions, molecules, annotations, labelDictionary
    ):
        """
        this model will go through the list of reactions and assign a 'modification' tag to those reactions where
        some kind of modification goes on aided through annotation information
        """
        rawReactions = [parseReactions(x) for x in reactions]
        equivalenceTranslator = self.processAnnotations(molecules, annotations)
        for reactionIndex in range(0, len(rawReactions)):
            for reactantIndex in range(0, len(rawReactions[reactionIndex])):
                tmp = []
                for chemicalIndex in range(
                    0, len(rawReactions[reactionIndex][reactantIndex])
                ):
                    tmp.extend(
                        list(
                            labelDictionary[
                                rawReactions[reactionIndex][reactantIndex][
                                    chemicalIndex
                                ]
                            ]
                        )
                    )
                rawReactions[reactionIndex][reactantIndex] = tmp
        # self.annotationClassificationHelper(rawReactions,equivalenceTranslator[-1])

    def userJsonToDataStructure(
        self,
        patternName,
        userEquivalence,
        dictionary,
        labelDictionary,
        equivalencesList,
    ):
        """
        converts a user defined species to an internal representation
        """
        tmp = st.Species()
        label = []
        for molecule in userEquivalence[1]:
            if molecule[0] == 0:
                labelDictionary[patternName] = 0
                return
            tmp2 = st.Molecule(molecule[0])
            for componentIdx in range(1, len(molecule), 2):
                tmp3 = st.Component(molecule[componentIdx])
                for bindStateIdx in range(0, len(molecule[componentIdx + 1]), 2):
                    if molecule[componentIdx + 1][bindStateIdx] == "b":
                        tmp3.addBond(molecule[componentIdx + 1][bindStateIdx + 1])
                    elif molecule[componentIdx + 1][bindStateIdx] == "s":
                        tmp3.addState("0")
                        tmp3.addState(molecule[componentIdx + 1][bindStateIdx + 1])
                        equivalencesList.append([patternName, molecule[0]])

                # tmp3.addState(molecule[2][2])

                tmp2.addComponent(tmp3)
            stmp = st.Species()
            stmp.addMolecule(deepcopy(tmp2))
            stmp.reset()
            # in case one definition overlaps another
            if molecule[0] in dictionary:
                dictionary[molecule[0]].extend(deepcopy(stmp))
            else:
                dictionary[molecule[0]] = deepcopy(stmp)
            labelDictionary[molecule[0]] = [(molecule[0],)]
            label.append(molecule[0])

            # for component in tmp2.components:
            #    if component.name == molecule[1]:
            #        component.setActiveState(molecule[2][1])
            tmp.addMolecule(tmp2)
        if patternName in dictionary:
            dictionary[patternName].extend(deepcopy(tmp))
        else:
            dictionary[patternName] = deepcopy(tmp)
        labelDictionary[patternName] = [tuple(label)]

    def getUserDefinedComplexes(self):
        dictionary = {}
        partialDictionary = {}
        userLabelDictionary = {}
        equivalencesList = []
        lexicalLabelDictionary = {}
        if self.speciesEquivalences is not None:
            speciesdictionary = self.loadConfigFiles(self.speciesEquivalences)
            userEquivalences = (
                speciesdictionary["complexDefinition"]
                if "complexDefinition" in speciesdictionary
                else None
            )
            for element in userEquivalences:
                self.userJsonToDataStructure(
                    element[0],
                    element,
                    dictionary,
                    userLabelDictionary,
                    equivalencesList,
                )

            complexEquivalences = speciesdictionary["modificationDefinition"]
            for element in complexEquivalences:
                userLabelDictionary[element] = [tuple(complexEquivalences[element])]

            partialUserEquivalences = (
                speciesdictionary["partialComplexDefinition"]
                if "partialComplexDefinition" in speciesdictionary
                else []
            )

            for element in partialUserEquivalences:
                self.userJsonToDataStructure(
                    tuple(sorted(element[0])), element, partialDictionary, {}, []
                )

        # stuff we got from string similarity
        for element in self.lexicalSpecies:
            self.userJsonToDataStructure(
                element[0],
                element,
                dictionary,
                lexicalLabelDictionary,
                equivalencesList,
            )
        return (
            dictionary,
            userLabelDictionary,
            lexicalLabelDictionary,
            partialDictionary,
        )
