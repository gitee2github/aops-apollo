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
from dataclasses import dataclass

import dnf
import hawkey
from dnf.cli.commands.updateinfo import UpdateInfoCommand
from dnf.i18n import _

from .hotpatch_updateinfo import HotpatchUpdateInfo


@dataclass
class DisplayItem:
    """
    Class for storing the formatting parameters and display lines.

    idw: the width of 'cve_id'
    tiw: the width of 'adv_type'
    ciw: the width of 'coldpatch'
    display_lines: [
            [cve_id, adv_type, coldpatch, hotpatch],
        ]
    """

    idw: int
    tiw: int
    ciw: int
    display_lines: list


@dnf.plugin.register_command
class HotUpdateinfoCommand(dnf.cli.Command):
    aliases = ['hot-updateinfo']
    summary = _('show hotpatch updateinfo')

    def __init__(self, cli):
        """
        Initialize the command
        """
        super(HotUpdateinfoCommand, self).__init__(cli)

    @staticmethod
    def set_argparser(parser):

        spec_action_cmds = ['list']
        parser.add_argument('spec_action', nargs=1, choices=spec_action_cmds, help=_('show updateinfo list'))

        with_cve_cmds = ['cve', 'cves']
        parser.add_argument('with_cve', nargs=1, choices=with_cve_cmds, help=_('show cves'))

    def configure(self):
        demands = self.cli.demands
        demands.sack_activation = True
        demands.available_repos = True

        self.filter_cves = self.opts.cves if self.opts.cves else None

    def run(self):
        self.hp_hawkey = HotpatchUpdateInfo(self.cli.base, self.cli)

        if self.opts.spec_action and self.opts.spec_action[0] == 'list' and self.opts.with_cve:
            self.display()

    def get_mapping_nevra_cve(self) -> dict:
        """
        Get cve nevra mapping based on the UpdateInfoCommand of 'dnf updateinfo list cves'

        Returns:
        {
            (nevra, advisory.updated):
                cve_id: {
                    (advisory.type, advisory.severity),
                    ...
                }
            ...
        }
        """
        # configure UpdateInfoCommand with 'dnf updateinfo list cves'
        updateinfo = UpdateInfoCommand(self.cli)
        updateinfo.opts = self.opts

        updateinfo.opts.spec_action = 'list'
        updateinfo.opts.with_cve = True
        updateinfo.opts.spec = '*'
        updateinfo.opts._advisory_types = set()
        updateinfo.opts.availability = 'available'
        self.updateinfo = updateinfo

        apkg_adv_insts = updateinfo.available_apkg_adv_insts(updateinfo.opts.spec)

        mapping_nevra_cve = dict()
        for apkg, advisory, _ in apkg_adv_insts:
            nevra = (apkg.name, apkg.evr, apkg.arch)
            for ref in advisory.references:
                if ref.type != hawkey.REFERENCE_CVE:
                    continue
                mapping_nevra_cve.setdefault((nevra, advisory.updated), dict())[ref.id] = (
                    advisory.type,
                    advisory.severity,
                )

        return mapping_nevra_cve

    def _filter_and_format_list_output(self, echo_lines: list, fixed_cve_id: set):
        """
        Only show specified cve information that have not been fixed, and format the display lines

        Returns:
            DisplayItem
        """
        # calculate the width of each column
        idw = tiw = ciw = 0
        format_lines = set()
        for echo_line in echo_lines:
            cve_id, adv_type, coldpatch, hotpatch = echo_line[0], echo_line[1], echo_line[2], echo_line[3]
            if self.filter_cves is not None and cve_id not in self.filter_cves:
                continue
            if cve_id in fixed_cve_id:
                continue
            if not isinstance(coldpatch, str):
                pkg_name, pkg_evr, pkg_arch = coldpatch
                coldpatch = '%s-%s.%s' % (pkg_name, pkg_evr, pkg_arch)

            idw = max(idw, len(cve_id))
            tiw = max(tiw, len(adv_type))
            ciw = max(ciw, len(coldpatch))
            format_lines.add((cve_id, adv_type, coldpatch, hotpatch))

        # sort format_lines according to the coldpatch and the hotpatch name
        format_lines = sorted(format_lines, key=lambda x: (x[2], x[3]))

        display_item = DisplayItem(idw=idw, tiw=tiw, ciw=ciw, display_lines=format_lines)

        return display_item

    def get_formatting_parameters_and_display_lines(self):
        """
        Append hotpatch information according to the output of 'dnf updateinfo list cves'

        echo lines:
            [
                [cve_id, adv_type, coldpatch, hotpatch]
            ]

        Returns:
            DisplayItem
        """

        def type2label(updateinfo, typ, sev):
            if typ == hawkey.ADVISORY_SECURITY:
                return updateinfo.SECURITY2LABEL.get(sev, _('Unknown/Sec.'))
            else:
                return updateinfo.TYPE2LABEL.get(typ, _('unknown'))

        mapping_nevra_cve = self.get_mapping_nevra_cve()
        echo_lines = []
        fixed_cve_id = set()
        iterated_cve_id = set()
        for ((nevra), aupdated), id2type in sorted(mapping_nevra_cve.items(), key=lambda x: x[0]):
            pkg_name, pkg_evr, pkg_arch = nevra
            for cve_id, atypesev in id2type.items():
                iterated_cve_id.add(cve_id)
                label = type2label(self.updateinfo, *atypesev)
                if cve_id not in self.hp_hawkey.hotpatch_cves or not self.hp_hawkey.hotpatch_cves[cve_id].hotpatches:
                    echo_line = [cve_id, label, nevra, '-']
                    echo_lines.append(echo_line)
                    continue

                for hotpatch in self.hp_hawkey.hotpatch_cves[cve_id].hotpatches:
                    echo_line = [cve_id, label, nevra, '-']
                    echo_lines.append(echo_line)
                    if hotpatch.src_pkg_nevre[0] != pkg_name:
                        continue
                    if hotpatch.state == self.hp_hawkey.INSTALLED:
                        # record the fixed cves
                        for cve_id in hotpatch.cves:
                            fixed_cve_id.add(cve_id)
                        echo_lines.pop()
                    elif hotpatch.state == self.hp_hawkey.INSTALLABLE:
                        echo_lines[-1][3] = hotpatch.nevra

        hp_cve_list = list(set(self.hp_hawkey.hotpatch_cves.keys()).difference(iterated_cve_id))
        for cve_id in hp_cve_list:
            for hotpatch in self.hp_hawkey.hotpatch_cves[cve_id].hotpatches:
                echo_line = [cve_id, hotpatch.advisory.severity + '/Sec.', '-', '-']
                if hotpatch.state == self.hp_hawkey.INSTALLED:
                    # record the fixed cves
                    fixed_cve_id.add(cve_id)
                    continue
                elif hotpatch.state == self.hp_hawkey.INSTALLABLE:
                    echo_line = [cve_id, hotpatch.advisory.severity + '/Sec.', '-', hotpatch.nevra]
                echo_lines.append(echo_line)

        display_item = self._filter_and_format_list_output(echo_lines, fixed_cve_id)

        return display_item

    def display(self):
        """
        Print the display lines according to the formatting parameters.
        """
        display_item = self.get_formatting_parameters_and_display_lines()
        idw, tiw, ciw, display_lines = display_item.idw, display_item.tiw, display_item.ciw, display_item.display_lines
        for display_line in display_lines:
            print(
                '%-*s %-*s %-*s %s'
                % (idw, display_line[0], tiw, display_line[1], ciw, display_line[2], display_line[3])
            )
