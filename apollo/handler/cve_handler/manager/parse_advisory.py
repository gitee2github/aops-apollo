#!/usr/bin/python3
# ******************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2021-2021. All rights reserved.
# licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN 'AS IS' BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.
# ******************************************************************************/
"""
Time:
Author:
Description: parse security advisory xml file, insert into database
"""
from xml.etree import cElementTree as ET
from xml.etree.ElementTree import ParseError
from collections import defaultdict

from aops_utils.log.log import LOGGER
from apollo.function.customize_exception import ParseAdvisoryError


__all__ = ["parse_security_advisory"]


def parse_security_advisory(xml_path):
    """
    parse the security advisory xml file, get the rows and docs for insertion
    Args:
        xml_path (str): cvrf xml file's path

    Returns:
        list: list of dict, each dict is a row for mysql Cve table
        list: list of dict, each dict is a row for mysql CveAffectedPkgs table
        list: list of dict, each dict is a document for es cve package index

    Raises:
        KeyError, ParseXmlError, IsADirectoryError
    """
    try:
        tree = ET.parse(xml_path)
    except ParseError:
        raise ParseAdvisoryError("The advisory may not in a correct xml format.")
    except FileNotFoundError:
        raise ParseAdvisoryError("File not found when parsing the xml.")

    root = tree.getroot()
    xml_dict = etree_to_dict(root)
    cve_rows, cve_pkg_rows, cve_pkg_docs = parse_cvrf_dict(xml_dict)
    return cve_rows, cve_pkg_rows, cve_pkg_docs


def etree_to_dict(node):
    """
    parse the cvrf xml str to dict. openEuler is supported, other OS has not been tested yet.
    Args:
        node (xml.etree.ElementTree.Element): xml ElementTree's node

    Returns:
        dict
    """
    node_name = node.tag.split("}")[1]
    node_dict = {node_name: {} if node.attrib else None}

    children = list(node)
    if children:
        dd = defaultdict(list)
        for dc in map(etree_to_dict, children):
            for k, v in dc.items():
                dd[k].append(v)
        node_dict = {node_name: {k: v[0] if len(v) == 1 else v for k, v in dd.items()}}
    # add node's attribute into node's dict
    if node.attrib:
        node_dict[node_name].update((k, v) for k, v in node.attrib.items())
    if node.text:
        text = node.text.strip()
        if children or node.attrib:
            if text:
                node_dict[node_name]['text'] = text
        else:
            node_dict[node_name] = text
    return node_dict


def parse_cvrf_dict(cvrf_dict):
    """
    parse cvrf's dict into mysql cve table rows, and es cve package index.
    Args:
        cvrf_dict (dict): cvrf(Common Vulnerability Reporting Framework) info dict

    Returns:
        list: list of dict, each dict is a row for mysql Cve table
        list: list of dict, each dict is a row for mysql CveAffectedPkgs table
        list: list of dict, each dict is a document for es cve package index

    Raises:
        ParseXmlError
    """
    publish_time = cvrf_dict["cvrfdoc"]["DocumentTracking"]["RevisionHistory"]["Revision"]["Date"]

    # affected package of this security advisory. joined with ',' if have multiple packages
    cvrf_note = cvrf_dict["cvrfdoc"]["DocumentNotes"]["Note"]
    affected_pkgs = ""
    for info in cvrf_note:
        if info["Title"] == "Affected Component":
            affected_pkgs = info["text"]
            break

    if not affected_pkgs:
        raise ParseAdvisoryError("Affected component (packages) is not list in this xml file.")

    pkg_list = affected_pkgs.split(",")
    arch_info_list = cvrf_dict["cvrfdoc"]["ProductTree"]["Branch"]
    cve_info_list = cvrf_dict["cvrfdoc"]["Vulnerability"]

    if isinstance(cve_info_list, dict):
        cve_info_list = [cve_info_list]

    try:
        cve_table_rows, cve_pkg_table_rows, cve_description = parse_cve_info(cve_info_list, pkg_list)
        es_cve_pkg_docs = parse_arch_info(arch_info_list, cve_description, publish_time)
    except (KeyError, TypeError) as error:
        LOGGER.error(error)
        raise ParseAdvisoryError("Some error happened when parsing the advisory xml.")
    return cve_table_rows, cve_pkg_table_rows, es_cve_pkg_docs


def parse_cve_info(cve_info_list, affected_pkgs):
    """
    get mysql Cve and CveAffectedPkgs table rows, and description info for elasticsearch
    Args:
        affected_pkgs (list): affected packages
        cve_info_list (list): list of dict. e.g.
            [{'CVE': 'CVE-2020-25681',
              'CVSSScoreSets': {'ScoreSet': {'BaseScore': '8.1',
                                             'Vector': 'AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H'}},
              'Notes': {'Note': {'Ordinal': '1',
                                 'Title': 'Vulnerability Description',
                                 'Type': 'General',
                                 'text': 'A long description',
                                 '{http://www.w3.org/XML/1998/namespace}lang': 'en'}},
              'Ordinal': '1',
              'ProductStatuses': {'Status': {'ProductID': ['openEuler-20.03-LTS',
                                                           'openEuler-20.03-LTS-SP1'],
                                             'Type': 'Fixed'}},
              'ReleaseDate': '2021-01-21',
              'Remediations': {'Remediation': {'DATE': '2021-01-21',
                                               'Description': 'dnsmasq security update',
                                               'Type': 'Vendor Fix',
                                               'URL': 'security advisory url'}},
              'Threats': {'Threat': {'Description': 'High', 'Type': 'Impact'}}}]

    Returns:
        list: list of dict for mysql Cve table. e.g.
            [{
                "cve_id": "cve-2021-1001",
                "publish_time": "2021-1-1",  // here is advisory's publish time actually
                "severity": "high",
                "cvss_score": "5.9",
                "reboot": False  // need reboot or not is default False for now
            }]
        list: list of dict for mysql CveAffectedPkgs table. e.g.
            [{"cve_id": "cve-2021-1001", "package": "redis"}]
        dict: cve id mapped with its description
    """
    cve_table_rows = []
    cve_pkg_table_rows = []
    cve_description = {}

    for cve_info in cve_info_list:
        cve_id = cve_info["CVE"]
        cve_row = {
            "cve_id": cve_id,
            "publish_time": cve_info["ReleaseDate"],
            "severity": cve_info["Threats"]["Threat"]["Description"],
            "cvss_score": cve_info["CVSSScoreSets"]["ScoreSet"]["BaseScore"],
            "reboot": False
        }
        cve_table_rows.append(cve_row)
        for pkg in affected_pkgs:
            cve_pkg_table_rows.append({"cve_id": cve_id, "package": pkg})

        # some cve may not have the 'text' key, which is description
        description = cve_info["Notes"]["Note"].get("text", "")
        cve_description[cve_id] = description

    return cve_table_rows, cve_pkg_table_rows, cve_description


def parse_arch_info(arch_info_list, cve_description, publish_time):
    """
    get es cve fixing documents for elasticsearch insertion
    Args:
        cve_description (dict): cve id mapped with its description
        publish_time (str): publish time of the security advisory. For same cve and os version,
                            new advisory will overwrite the old one
        arch_info_list (list): affected os version and arch's packages' info. e.g.
            [{'Name': 'openEuler',
              'Type': 'Product Name',
              'FullProductName': [{'CPE': 'cpe:/a:openEuler:openEuler:20.03-LTS-SP1',
                                   'ProductID': 'openEuler-20.03-LTS-SP1',
                                   'text': 'openEuler-20.03-LTS-SP1'},
                                  {'CPE': 'cpe:/a:openEuler:openEuler:20.03-LTS-SP2',
                                   'ProductID': 'openEuler-20.03-LTS-SP2',
                                   'text': 'openEuler-20.03-LTS-SP2'}]},
             {'Name': 'noarch',
              'Type': 'Package Arch',
              'FullProductName': [{'CPE': 'cpe:/a:openEuler:openEuler:20.03-LTS-SP1',
                                   'ProductID': 'rubygem-bundler-2.2.33-1',
                                   'text': 'rubygem-bundler-2.2.33-1.oe1.noarch.rpm'},
                                  {'CPE': 'cpe:/a:openEuler:openEuler:20.03-LTS-SP1',
                                   'ProductID': 'rubygem-bundler-help-2.2.33-1',
                                   'text': 'rubygem-bundler-help-2.2.33-1.oe1.noarch.rpm'},
                                  {'CPE': 'cpe:/a:openEuler:openEuler:20.03-LTS-SP2',
                                   'ProductID': 'rubygem-bundler-help-2.2.33-1',
                                   'text': 'rubygem-bundler-help-2.2.33-1.oe1.noarch.rpm'},
                                  {'CPE': 'cpe:/a:openEuler:openEuler:20.03-LTS-SP2',
                                   'ProductID': 'rubygem-bundler-2.2.33-1',
                                   'text': 'rubygem-bundler-2.2.33-1.oe1.noarch.rpm'}]},
             {'Name': 'src',
              'Type': 'Package Arch',
              'FullProductName': [{'CPE': 'cpe:/a:openEuler:openEuler:20.03-LTS-SP1',
                                   'ProductID': 'rubygem-bundler-2.2.33-1',
                                   'text': 'rubygem-bundler-2.2.33-1.oe1.src.rpm'},
                                  {'CPE': 'cpe:/a:openEuler:openEuler:20.03-LTS-SP2',
                                   'ProductID': 'rubygem-bundler-2.2.33-1',
                                   'text': 'rubygem-bundler-2.2.33-1.oe1.src.rpm'}]}]
    Returns:
        list: e.g.
            [{'cve_id': 'CVE-2021-43809',
              'description': 'a long description',
              'os_list': [{'arch_list': [{'arch': 'noarch',
                                          'package': ['rubygem-bundler-2.2.33-1.oe1.noarch.rpm',
                                                      'rubygem-bundler-help-2.2.33-1.oe1.noarch.rpm']},
                                         {'arch': 'src',
                                          'package': ['rubygem-bundler-2.2.33-1.oe1.src.rpm']}],
                           'os_version': 'openEuler:20.03-LTS-SP1',
                           'update_time': '2021-12-31'}]}]  // SP2 dict is omitted here
    """
    def defaultdict_list():
        return defaultdict(list)

    # process xml data
    os_dict = defaultdict(defaultdict_list)
    for arch_info in arch_info_list:
        if arch_info["Type"] == "Product Name":
            continue
        arch = arch_info["Name"]
        pkg_info_list = arch_info["FullProductName"]
        if isinstance(pkg_info_list, dict):
            os_version = pkg_info_list["CPE"].split(":", 3)[-1]
            os_dict[os_version][arch].append(pkg_info_list["text"])
            continue
        for pkg_info in pkg_info_list:
            # split the cpe value 3 times and get the last part
            os_version = pkg_info["CPE"].split(":", 3)[-1]
            os_dict[os_version][arch].append(pkg_info["text"])

    # change to the format we want
    os_list = []
    for os_version, arch_dict in os_dict.items():
        arch_list = []
        for arch_name, arch_pkgs in arch_dict.items():
            arch_list.append({"arch": arch_name, "package": arch_pkgs})
        current_os_dict = {"os_version": os_version, "update_time": publish_time, "arch_list": arch_list}
        os_list.append(current_os_dict)

    doc_list = []
    for cve_id, description in cve_description.items():
        doc_dict = {"cve_id": cve_id, "description": description, "os_list": os_list}
        doc_list.append(doc_dict)
    return doc_list
