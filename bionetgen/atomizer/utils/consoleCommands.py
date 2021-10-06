# -*- coding: utf-8 -*-
"""
Created on Mon Sep  2 18:11:35 2013

@author: proto
"""

import platform

if platform.system() != "Windows":
    import pexpect
else:
    import winpexpect
import subprocess
import os

from os.path import expanduser, join

home = expanduser("~")

bngExecutable = join(home, "workspace", "RuleWorld", "bionetgen", "bng2", "BNG2.pl")


def setBngExecutable(executable):
    global bngExecutable
    bngExecutable = executable


def getBngExecutable():
    return bngExecutable


def bngl2xml(bnglFile, timeout=60):
    try:
        if platform.system() != "Windows":
            bngconsole = pexpect.spawn(
                "{0} --console".format(getBngExecutable()), timeout=timeout
            )
        else:
            bngconsole = winpexpect.winspawn(
                "perl {0} --console".format(getBngExecutable()), timeout=timeout
            )
        bngconsole.expect("BNG>")
        bngconsole.sendline("load {0}".format(bnglFile))
        bngconsole.expect("BNG>")
        bngconsole.sendline("action writeXML()")
        bngconsole.expect("BNG>")
        bngconsole.close()
    except pexpect.TIMEOUT:
        subprocess.call(["killall", "bngdev"])


def bngl2sbml(bnglFile, timeout=60):
    try:
        bngconsole = pexpect.spawn(
            "{0} --console".format(getBngExecutable()), timeout=timeout
        )
        bngconsole.expect("BNG>")
        bngconsole.sendline("load {0}".format(bnglFile))
        bngconsole.expect("BNG>")
        bngconsole.sendline("action generate_network()")
        bngconsole.expect("BNG>")
        bngconsole.sendline("action writeSBML()")
        bngconsole.expect("BNG>")
        bngconsole.close()
    except pexpect.TIMEOUT:
        subprocess.call(["killall", "bngdev"])


def correctness(bnglFile):
    bngconsole = pexpect.spawn("{0} --console".format(getBngExecutable()))
    bngconsole.expect("BNG>")
    bngconsole.sendline("load {0}".format(bnglFile))
    bngconsole.expect("BNG>")
    output = bngconsole.before
    bngconsole.close()
    if "ERROR" in output in output:
        return False
    return True


def writeNetwork(bnglFile):
    bngconsole = pexpect.spawn("{0} --console".format(getBngExecutable()))
    bngconsole.expect("BNG>")
    bngconsole.sendline("load {0}".format(bnglFile))
    bngconsole.expect("BNG>")
    bngconsole.sendline("action generate_network()")
    bngconsole.expect("BNG>")
    bngconsole.close()


def generateGraph(bnglFile, graphType, options=[]):
    directory = os.sep.join(bnglFile.split(os.sep)[:-1])
    bngconsole = pexpect.spawn("{0} --console".format(getBngExecutable()))
    bngconsole.expect("BNG>")
    bngconsole.sendline("load {0}".format(bnglFile))
    bngconsole.expect("BNG>")
    options = ["{0}=>1".format(x) for x in options]
    options = ", ".join(options)
    if graphType == "regulatory":
        bngconsole.sendline("action visualize({{{0}}})".format(options))
    elif graphType == "contactmap":
        bngconsole.sendline('action visualize({type=>"contactmap"})')
    else:
        return False
    bngconsole.expect("BNG>")
    bngconsole.close()
    return True


if __name__ == "__main__":
    print(bngl2xml("/tmp/tmpIhm3Ej.bngl"))
