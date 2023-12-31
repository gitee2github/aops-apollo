#!/usr/bin/python3
# ******************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2023-2023. All rights reserved.
# licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.
# ******************************************************************************/
import datetime
import gzip
import os
import re
import xml.etree.ElementTree as ET

from .baseclass import Hotpatch, Cve, Advisory
from .syscare import Syscare


class HotpatchUpdateInfo(object):
    """
    Hotpatch relevant updateinfo processing
    """

    UNINSTALLABLE = 0
    INSTALLED = 1
    INSTALLABLE = 2

    def __init__(self, base, cli):
        self.base = base
        self.cli = cli
        # dict {advisory_id: Advisory}
        self._hotpatch_advisories = {}
        # dict {cve_id: Cve}
        self._hotpatch_cves = {}
        # list [{'Uuid': uuid, 'Name':name, 'Status': status}]
        self._hotpatch_status = []

        self.init_hotpatch_info()

    def init_hotpatch_info(self):
        """
        Initialize hotpatch information
        """
        self._get_installed_pkgs()
        self._parse_and_store_hotpatch_info_from_updateinfo()
        self._init_hotpatch_status_from_syscare()
        self._init_hotpatch_state()

    @property
    def hotpatch_cves(self):
        return self._hotpatch_cves

    @property
    def hotpatch_status(self):
        return self._hotpatch_status

    def _get_installed_pkgs(self):
        """
        Get installed packages by setting the hawkey
        """
        sack = self.base.sack
        # the latest installed packages
        q = sack.query().installed().latest(1)
        # plus packages of the running kernel
        kernel_q = sack.query().filterm(empty=True)
        kernel = sack.get_running_kernel()
        if kernel:
            kernel_q = kernel_q.union(sack.query().filterm(sourcerpm=kernel.sourcerpm))
        q = q.union(kernel_q.installed())
        q = q.apply()

        self._inst_pkgs_query = q

    def _parse_and_store_hotpatch_info_from_updateinfo(self):
        """
        Initialize hotpatch information from repos
        """
        # get xxx-updateinfo.xml.gz file paths by traversing the system_cachedir(/var/cache/dnf)
        system_cachedir = self.cli.base.conf.system_cachedir
        all_repos = self.cli.base.repos
        map_repo_updateinfoxml = {}

        for file in os.listdir(system_cachedir):
            file_path = os.path.join(system_cachedir, file)
            if os.path.isdir(file_path):
                repodata_path = os.path.join(file_path, "repodata")
                if not os.path.isdir(repodata_path):
                    continue

                for xml_file in os.listdir(repodata_path):
                    # the hotpatch relevant updateinfo is recorded in xxx-updateinfo.xml.gz
                    if "updateinfo" in xml_file:
                        repo_name = file.rsplit("-")[0]
                        cache_updateinfo_xml_path = os.path.join(repodata_path, xml_file)
                        map_repo_updateinfoxml[repo_name] = cache_updateinfo_xml_path

        # only hotpatch relevant updateinfo from enabled repos are parsed and stored
        for repo in all_repos.iter_enabled():
            repo_id = repo.id
            if repo_id in map_repo_updateinfoxml:
                updateinfoxml_path = map_repo_updateinfoxml[repo_id]
                self._parse_and_store_from_xml(updateinfoxml_path)

    def _parse_pkglist(self, pkglist):
        """
        Parse the pkglist information, filter the hotpatches with different arches
        """
        hotpatches = []
        hot_patch_collection = pkglist.find('hot_patch_collection')
        arches = self.base.sack.list_arches()
        if not hot_patch_collection:
            return hotpatches
        for package in hot_patch_collection.iter('package'):
            hotpatch = {key: value for key, value in package.items()}
            if hotpatch['arch'] not in arches:
                continue
            hotpatch['filename'] = package.find('filename').text
            hotpatches.append(hotpatch)
        return hotpatches

    def _parse_references(self, reference):
        """
        Parse the reference information, check whether the 'id' is missing
        """
        cves = []
        for ref in reference:
            cve = {key: value for key, value in ref.items()}
            if 'id' not in cve:
                continue
            cves.append(cve)
        return cves

    def _verify_date_str_lawyer(self, datetime_str: str) -> str:
        """
        Check whether the 'datetime' field is legal, if not return default value
        """
        if datetime_str.isdigit() and len(datetime_str) == 10:
            datetime_str = int(datetime_str)
            datetime_str = datetime.datetime.fromtimestamp(datetime_str).strftime("%Y-%m-%d %H:%M:%S")
        try:
            datetime.datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
            return datetime_str
        except ValueError:
            return "1970-01-01 08:00:00"

    def _parse_advisory(self, update):
        """
        Parse the advisory information: check whether the 'datetime' field is legal, parse the 'references'
        field and the 'pkglist' field, save 'type' information
        """
        advisory = {}
        for node in update:
            if node.tag == 'datetime':
                advisory[node.tag] = self._verify_date_str_lawyer(update.find(node.tag).text)
            elif node.tag == 'references':
                advisory[node.tag] = self._parse_references(node)
            elif node.tag == 'pkglist':
                advisory['hotpatches'] = self._parse_pkglist(node)
            else:
                advisory[node.tag] = update.find(node.tag).text
        advisory['adv_type'] = update.get('type')
        return advisory

    def _store_advisory_info(self, advisory_kwargs: dict()):
        """
        Instantiate Cve, Hotpatch and Advisory object according to the advisory kwargs
        """
        advisory_references = advisory_kwargs.pop('references')
        advisory_hotpatches = advisory_kwargs.pop('hotpatches')
        advisory = Advisory(**advisory_kwargs)
        advisory_cves = {}
        for cve_kwargs in advisory_references:
            cve = Cve(**cve_kwargs)
            self._hotpatch_cves[cve.cve_id] = cve
            advisory_cves[cve.cve_id] = cve
        advisory.cves = advisory_cves

        for hotpatch_kwargs in advisory_hotpatches:
            # parse the id string of the package to list
            # e.g. parse the id of "CVE-2021-2023,CVE-2021-2024" to ["CVE-2021-2023", "CVE-2021-2024"]
            hotpatch_ref_id = hotpatch_kwargs.pop('id')
            hotpatch_ref_id = hotpatch_ref_id.split(',')

            hotpatch = Hotpatch(**hotpatch_kwargs)
            hotpatch.advisory = advisory
            hotpatch.cves = hotpatch_ref_id

            advisory.add_hotpatch(hotpatch)

            for ref_id in hotpatch_ref_id:
                advisory_cves[ref_id].add_hotpatch(hotpatch)

        self._hotpatch_advisories[advisory_kwargs['id']] = advisory

    def _init_hotpatch_state(self):
        """
        Initialize the hotpatch state

        each hotpatch has three states:
        1. UNINSTALLABLE: can not be installed due to the source package version mismatch
        2. INSTALLED: has been installed and actived in syscare
        3. INSTALLABLE: can be installed

        """
        for advisory in self._hotpatch_advisories.values():
            for hotpatch in advisory.hotpatches:
                src_pkg_name, src_pkg_version, src_pkg_release = hotpatch.src_pkg_nevre
                inst_pkgs = self._inst_pkgs_query.filter(name=src_pkg_name)
                hotpatch.state = self.UNINSTALLABLE
                # check whether the relevant source package is installed on this machine
                if not inst_pkgs:
                    continue
                for inst_pkg in inst_pkgs:
                    inst_pkg_vere = '%s-%s' % (inst_pkg.version, inst_pkg.release)
                    hp_vere = '%s-%s' % (src_pkg_version, src_pkg_release)
                    if hp_vere != inst_pkg_vere:
                        continue
                    elif self._get_hotpatch_status_in_syscare(hotpatch) in ('ACTIVED', "ACCEPTED"):
                        hotpatch.state = self.INSTALLED
                    else:
                        hotpatch.state = self.INSTALLABLE

    def _parse_and_store_from_xml(self, updateinfoxml):
        """
        Parse and store hotpatch update information from xxx-updateinfo.xml.gz

        xxx-updateinfo.xml.gz e.g.

        <?xml version="1.0" encoding="UTF-8"?>
        <updates>
            <update from="openeuler.org" type="security" status="stable">
                <id>openEuler-SA-2022-1</id>
                <title>An update for mariadb is now available for openEuler-22.03-LTS</title>
                <severity>Important</severity>
                <release>openEuler</release>
                <issued date="2022-04-16"></issued>
                <references>
                    <reference href="https://nvd.nist.gov/vuln/detail/CVE-2021-1111" id="CVE-2021-1111" title="CVE-2021-1111" type="cve"></reference>
                    <reference href="https://nvd.nist.gov/vuln/detail/CVE-2021-1112" id="CVE-2021-1112" title="CVE-2021-1112" type="cve"></reference>
                </references>
                <description>patch-redis-6.2.5-1-HP001.(CVE-2022-24048)</description>
                <pkglist>
                <hot_patch_collection>
                    <name>openEuler</name>
                    <package arch="aarch64" name="patch-redis-6.2.5-1-HP001" release="1" version="1" id="CVE-2021-1111" >
                        <filename>patch-redis-6.2.5-1-HP001-1-1.aarch64.rpm</filename>
                    </package>
                    <package arch="x86_64" name="patch-redis-6.2.5-1-HP001" release="1" version="1" id="CVE-2021-1111">
                        <filename>patch-redis-6.2.5-1-HP001-1-1.x86_64.rpm</filename>
                    </package>
                    <package arch="aarch64" name="patch-redis-6.2.5-1-HP002" release="1" version="1" id="CVE-2021-1111,CVE-2021-1112">
                        <filename>patch-redis-6.2.5-1-HP002-1-1.aarch64.rpm</filename>
                    </package>
                    <package arch="x86_64" name="patch-redis-6.2.5-1-HP002" release="1" version="1" id="CVE-2021-1111,CVE-2021-1112">
                        <filename>patch-redis-6.2.5-1-HP002-1-1.x86_64.rpm</filename>
                    </package>
                </hot_patch_collection>
                </pkglist>
            </update>
            ...
        </updates>
        """
        content = gzip.open(updateinfoxml)
        tree = ET.parse(content)
        root = tree.getroot()
        for update in root.iter('update'):
            # check whether the hotpatch relevant package information is in each advisory
            if not update.find('pkglist/hot_patch_collection'):
                continue
            advisory = self._parse_advisory(update)
            self._store_advisory_info(advisory)

    def _init_hotpatch_status_from_syscare(self):
        """
        Initialize hotpatch status from syscare
        """
        self._hotpatch_status = Syscare().list()

        self._hotpatch_state = {}
        for hotpatch_info in self._hotpatch_status:
            self._hotpatch_state[hotpatch_info['Name']] = hotpatch_info['Status']

    def _get_hotpatch_status_in_syscare(self, hotpatch: Hotpatch) -> str:
        """
        Get hotpatch status in syscare
        """
        if hotpatch.syscare_name not in self._hotpatch_state:
            return ''
        return self._hotpatch_state[hotpatch.syscare_name]

    def get_hotpatches_from_cve(self, cves: list[str]) -> dict():
        """
        Get hotpatches from specified cve. If there are several hotpatches for the same source package for a cve, only return the
        hotpatch with the highest version.

        Args:
            cves: [cve_id_1, cve_id_2]

        Returns:
        {
            cve_id_1: [hotpatch1],
            cve_id_2: []
        }
        """
        mapping_cve_hotpatches = dict()
        for cve_id in cves:
            mapping_cve_hotpatches[cve_id] = []
            if cve_id not in self.hotpatch_cves:
                continue
            # find the hotpatch with the highest version for the same source package
            mapping_src_pkg_to_hotpatches = dict()
            # check whether the cve is fixed
            is_cve_fixed = False
            for hotpatch in self.hotpatch_cves[cve_id].hotpatches:
                if hotpatch.state == self.INSTALLED:
                    is_cve_fixed = True
                if hotpatch.state == self.INSTALLABLE:
                    mapping_src_pkg_to_hotpatches.setdefault(hotpatch.src_pkg, []).append(
                        [hotpatch.hotpatch_name, hotpatch]
                    )
            # do not return the releated hotpatches if the cve is fixed
            if is_cve_fixed:
                continue
            for src_pkg, hotpatches in mapping_src_pkg_to_hotpatches.items():
                # extract the number in HPxxx and sort hotpatches in descending order according to the number
                hotpatches = sorted(hotpatches, key=lambda x: int(re.findall("\d+", x[0])[0]), reverse=True)
                mapping_cve_hotpatches[cve_id].append(hotpatches[0][1].nevra)

        return mapping_cve_hotpatches

    def get_hotpatches_from_advisories(self, advisories: list[str]) -> dict():
        """
        Get hotpatches from specified advisories

        Args:
            advisories: [advisory_id_1, advisory_id_2]

        Return:
        {
            advisory_id_1: [hotpatch1],
            advisory_id_2: []
        }
        """
        mapping_advisory_hotpatches = dict()
        for advisory_id in advisories:
            mapping_advisory_hotpatches[advisory_id] = []
            if advisory_id not in self._hotpatch_advisories:
                continue
            advisory = self._hotpatch_advisories[advisory_id]
            for hotpatch in advisory.hotpatches:
                if hotpatch.state == self.INSTALLABLE:
                    mapping_advisory_hotpatches[advisory_id].append(hotpatch.nevra)
        return mapping_advisory_hotpatches
