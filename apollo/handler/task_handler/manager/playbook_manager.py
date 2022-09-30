#!/usr/bin/python3
# ******************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2021-2022. All rights reserved.
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
Description: playbook creating related function
"""
import os
import uuid
import json

from aops_utils.restful.status import DATABASE_CONNECT_ERROR, NO_DATA, SUCCEED, WRONG_DATA
from aops_utils.log.log import LOGGER
from apollo.handler.task_handler.config import\
    YAML, INVENTORY_DIR, PLAYBOOK_DIR, REPO_DIR, DIR_MAP
from apollo.handler.task_handler.template import\
    COPY_SCRIPT_TEMPLATE, REBOOT_TEMPLATE
from apollo.database.proxy.task import TaskProxy
from apollo.database.proxy.repo import RepoProxy
from apollo.database import SESSION


def yaml_write(file_dir, file_name, content):
    """
    Write dict to yaml file

    Args:
        file_dir (str): directory
        file_name (str): name
        content (dict)
    """
    if not os.path.exists(file_dir):
        os.makedirs(file_dir)
    file_path = os.path.join(file_dir, file_name)
    with open(file_path, 'w', encoding='utf-8') as stream:
        YAML.dump(content, stream)


def is_existed(file_name, file_type='inventory'):
    """
    Judge whether the playbook, inventory, repo exist.

    Args:
        file_name (str)
        file_type (str, optional): Defaults to 'inventory'.

    Returns:
        bool
    """
    file_dir = DIR_MAP.get(file_type)
    if file_dir is None:
        return False

    file_path = os.path.join(file_dir, file_name)
    return os.path.exists(file_path)


def get_cve_list(info):
    """
    Get the cve id list from the task info

    Args:
        info (list): task info

    Returns:
        list: cve id list
    """
    cve_list = []
    for item in info:
        cve_id = item.get('cve_id')
        if cve_id is not None:
            cve_list.append(cve_id)

    return cve_list


class Playbook():
    """
    Base playbook manager.
    """

    def __init__(self, task_id, write=False, check_items=None):
        """
        Args:
            task_id (str)
            write (bool, optional): whether to write to local file. Defaults to False.
            check_items (list, optional): check items before executing task. Defaults to None.
        """
        self.task_id = task_id
        self.write = write
        self.check_items = check_items
        if self.check_items:
            self.check_condition = ' and '.join(
                "check_" + item + '_result.rc == 0'
                for item in check_items)

    @staticmethod
    def add_check_items(playbook, check_items):
        """
        Add check items to playbook, in certain format.

        Args:
            playbook (list)
            check_items (list)

        Returns:
            list
        """
        for check_item in check_items:
            playbook.append({
                'hosts': 'total_hosts',
                'gather_facts': False,
                'tasks': [
                    {
                        'name': 'check ' + check_item,
                        'become': True,
                        'become_user': 'root',
                        'shell': 'sh /tmp/check.sh ' + check_item,
                        'register': 'check_{}_result'.format(check_item),
                        'ignore_errors': True
                    }
                ]
            })
        return playbook

    def create_check_task(self, template=COPY_SCRIPT_TEMPLATE):
        """
        Add check task to playbook according to check items.

        Args:
            template (dict): playbook template, Defaults to COPY_SCRIPT_TEMPLATE.

        Returns:
            list
        """
        playbook = []
        # if need check, add check task
        if self.check_items:
            playbook.append(template)
            self.add_check_items(playbook, self.check_items)

        return playbook

    def create_inventory(self, info):
        """
        Create inventory for playbook.

        Args:
            info (list): host info that need repo setting.

        Returns:
            dict: inventory
        """
        hosts = {'total_hosts': {'hosts': {}}}
        for host in info:
            hosts['total_hosts']['hosts'][host['host_name']] = {
                'ansible_python_interpreter': '/usr/bin/python3',
                'ansible_host': host['host_ip']}

        if self.write:
            yaml_write(INVENTORY_DIR, self.task_id, hosts)

        return hosts

    @staticmethod
    def _check_file(file_dir, file_name, proxy, item, task_id):
        """
        Check file in local, re-dump if it does not exist.

        Args:
            file_dir (str): file directory
            file_name (str): file name
            proxy (object): database proxy instance
            item (str): check playbook or inventory
            task_id (str)

        Returns:
            bool
        """
        file_path = os.path.join(file_dir, file_name)
        # when the file is not existed in local
        if not os.path.exists(file_path):
            LOGGER.info("the queried %s of task %s doesn't exist in local,\
                try to query from database", item, task_id)
            func = getattr(TaskProxy, 'get_task_ansible_info')
            status_code, content = func(proxy, task_id, item)
            if status_code != SUCCEED or len(content) == 0:
                LOGGER.error(
                    "the queried %s of task %s doesn't exist in database", item, task_id)
                return False
            if not os.path.exists(file_dir):
                os.makedirs(file_dir)
            with open(file_path, 'w', encoding='utf-8') as stream:
                YAML.dump(json.loads(content), stream)

        return True

    @classmethod
    def check_pb_and_inventory(cls, task_id, proxy):
        """
        Check playbook and inventory in the local file.

        Args:
            task_id (str)
            proxy (object): database proxy instance

        Returns:
            bool
        """
        pb_file_name = "{}.yml".format(task_id)
        return Playbook._check_file(PLAYBOOK_DIR, pb_file_name, proxy, 'playbook', task_id) and\
            Playbook._check_file(INVENTORY_DIR, task_id,
                                 proxy, 'inventory', task_id)


class CveFixPlaybook(Playbook):
    """
    Playbook creater for cve fixing.
    """

    def __init__(self, task_id, write=False, check_items=None, function='yum'):
        """
        Args:
            task_id (str)
            write (bool, optional): whether to write to local file. Defaults to False.
            check_items (list, optional): Defaults to None.
            function (str, optional): choose how to fix cve, please refer to readme.
                                      Defaults to 'yum'.
        """
        self.function = function
        super().__init__(task_id, write, check_items)

    def create_fix_task(self, cve_id, func_param):
        """
        Create fix task section in playbook according to certain function.

        Args:
            cve_id (str): name of cve
            func_param (dict): parameter of the certain function

        Returns:
            dict: task section
        """
        temp = {
            "hosts": cve_id,
            "gather_facts": False,
            "tasks": [
                {
                    "name": cve_id,
                    "ignore_errors": True,
                    "become": True,
                    "become_user": "root"
                }
            ]
        }
        temp['tasks'][0].update(func_param)
        if self.check_items:
            temp['tasks'][0].update({"when": self.check_condition})
        return temp

    def create_fix_param(self, cve_id, package_info):
        """
        Get fix description according to certain function

        Args:
            cve_id (str)
            package_info (dict): package info about cve

        Returns:
            dict: fix description
        """
        if self.function == 'rpm':
            package = package_info.get(cve_id)
            if package is None:
                LOGGER.error("There is no package info about the %s,\
                    so the fix function %s is not feasible.", cve_id, self.function)
                return {}
            func_param = {
                "yum": {
                    "state": "present",
                    "name": package
                }
            }
        else:
            func_param = {
                "shell": "yum upgrade -y --cve=" + cve_id
            }

        return func_param

    def create_fix_inventory(self, basic_info):
        """
        Create inventory

        Args:
            basic_info (list): basic info about cve and host, e.g.
                [
                    {
                        "cve_id": "cve-11-11",
                        "host_info": [
                            {
                                "host_name": "name1",
                                "host_ip": "11.1.1.1"
                            }
                        ],
                        "reboot": True
                    }
                ]

        Returns:
            dict
        """
        hosts = {'total_hosts': {'hosts': {}}, "reboot_hosts": {'hosts': {}}}
        for info in basic_info:
            cve_id = info.get('cve_id')
            host_info = info.get('host_info')
            reboot = info.get('reboot', False)
            if not all([cve_id, host_info]):
                continue
            hosts[cve_id] = {"hosts": {}}
            for host in host_info:
                hosts['total_hosts']['hosts'][host['host_name']] =\
                    hosts[cve_id]['hosts'][host['host_name']] =\
                    {'ansible_python_interpreter': '/usr/bin/python3',
                     'ansible_host': host['host_ip']}
                if reboot:
                    hosts['reboot_hosts']['hosts'][host['host_name']] =\
                        {'ansible_python_interpreter': '/usr/bin/python3',
                         'ansible_host': host['host_ip']}

        if len(hosts['reboot_hosts']['hosts']) == 0:
            hosts.pop('reboot_hosts')

        if self.write:
            yaml_write(INVENTORY_DIR, self.task_id, hosts)

        return hosts

    def create_fix_playbook(self, basic_info, package_info):
        """
        Create cve fixing playbook according to the task info.

        Args:
            basic_info (list): basic info about cve and host.
            package_info (dict): package info for each cve, e.g.
                {
                    "cve-11-11": ["redis-xxx.rpm", "redis-debug-xxx.rpm"]
                }

        Returns:
            list: playbook
        """
        playbook = self.create_check_task()

        reboot = False
        for info in basic_info:
            cve_id = info.get('cve_id')
            if cve_id is None:
                continue
            if not reboot and info.get('reboot', False):
                reboot = True

            # add task
            func_param = self.create_fix_param(cve_id, package_info)
            if not func_param:
                continue
            temp = self.create_fix_task(cve_id, func_param)
            playbook.append(temp)

        if reboot:
            playbook.append(REBOOT_TEMPLATE)

        if self.write:
            yaml_write(PLAYBOOK_DIR, self.task_id + '.yml', playbook)

        return playbook

    @staticmethod
    def create_rollback_param(package):
        """
        Get rollback description according to certain function.

        Args:
            package (list): package list that need rollbacked

        Returns:
            dict: rollback description
        """
        func_param = {
            "shell": " ".join(package)
        }

        return func_param

    @staticmethod
    def create_rollback_task(cve_id, func_param):
        """
        Create rollback task section in playbook according to certain function.

        Args:
            cve_id (str): name of cve
            func_param (dict): parameter of the certain function

        Returns:
            dict: task section
        """
        temp = {
            "hosts": cve_id,
            "gather_facts": False,
            "tasks": [
                {
                    "name": cve_id,
                    "ignore_errors": True,
                    "become": True,
                    "become_user": "root"
                }
            ]
        }
        temp['tasks'][0].update(func_param)
        return temp

    def create_rollback_playbook(self, cve_list, package_info):
        """
        Create rollback playbook for certain cve.

        Args:
            cve_list (list): cve id list
            package_info (dict): related package of cve

        Returns:
            list: playbook content
            str: task id for the rollback
        """
        playbook = []
        task_id = str(uuid.uuid1()).replace('-', '')

        for cve_id in cve_list:
            package = package_info.get(cve_id)
            if not package:
                LOGGER.warning(
                    "Since there is no package info about the cve %s, ignore it.", cve_id)
                continue
            func_param = self.create_rollback_param(package)
            temp = self.create_rollback_task(cve_id, func_param)
            playbook.append(temp)

        if self.write:
            yaml_write(PLAYBOOK_DIR, task_id + '.yml', playbook)

        return playbook, task_id


class CveScanPlaybook(Playbook):
    """
    Playbook creater for cve scanning.
    """

    def create_playbook(self):
        """
        Create cve scanning playbook

        Returns:
            list
        """
        playbook = [
            {
                "hosts": "total_hosts",
                "gather_facts": False,
                "tasks": [
                    {
                        "name": "scan",
                        "become": True,
                        "become_user": "root",
                        "shell": "yum updateinfo list cves installed"
                    }
                ]
            }
        ]

        if self.write:
            yaml_write(PLAYBOOK_DIR, self.task_id + '.yml', playbook)

        return playbook


class RepoPlaybook(Playbook):
    """
    Playbook creater for repo setting.
    """

    def __init__(self, task_id, write=False, check_items=None):
        """
        Args:
            task_id (str)
            write (bool, optional): whether to write to local file. Defaults to False.
            check_items (list, optional): Defaults to None.
        """
        self.repo_path = ""
        super().__init__(task_id, write, check_items)

    @staticmethod
    def check_repo_attr(repo_info, host_info):
        """
        Check the repo version and os version is whether matched.

        Args:
            repo_info (dict)
            host_info (list)

        Returns:
            bool
        """
        return True

    def check_repo_data(self, repo_name, username, repo_info):
        """
        Check the repo that the task uses is whether valid

        Args:
            repo_name (str): repo name
            username (str)
            repo_info (dict)

        Returns:
            bool
        """
        repo_data = repo_info.get('repo_data')
        if not repo_data:
            return False

        # check local file.
        repo_dir = os.path.join(REPO_DIR, username)
        repo_path = os.path.join(repo_dir, '{}.repo'.format(repo_name))
        self.repo_path = repo_path
        if not os.path.exists(repo_dir):
            os.makedirs(repo_dir)
        with open(repo_path, 'w', encoding='utf-8') as file_io:
            file_io.write(repo_data)

        return True

    def check_repo(self, repo_name, username, host_info=None):
        """
        Check the repo that the task uses is whether valid

        Args:
            repo_name (str): repo name
            username (str)

        Returns:
            int: status code
        """
        # query from database.
        repo_proxy = RepoProxy()
        if not repo_proxy.connect(SESSION):
            return DATABASE_CONNECT_ERROR

        status_code, result = repo_proxy.get_repo(
            {'username': username, 'repo_name_list': [repo_name]})
        if status_code != SUCCEED:
            return status_code

        repo_info = result.get('result')
        if len(repo_info) != 1:
            return WRONG_DATA

        if host_info and not self.check_repo_attr(repo_info[0], host_info):
            return WRONG_DATA

        if not self.check_repo_data(repo_name, username, repo_info[0]):
            return NO_DATA

        return SUCCEED

    def create_playbook(self):
        """
        Create playbook for repo setting task.

        Args:

        Returns:
            list: playbook
        """
        playbook = self.create_check_task()
        playbook.append(
            {
                'hosts': 'total_hosts',
                "gather_facts": False,
                'tasks': [
                    {
                        'name': 'copy repo',
                        'become': True,
                        'become_user': 'root',
                        'copy': {
                            'src': self.repo_path,
                            'dest': '/etc/yum.repos.d/aops-update.repo'
                        }
                    },
                    {
                        'name': 'set repo',
                        'become': True,
                        'become_user': 'root',
                        'shell': 'yum makecache'
                    }
                ]
            })

        if self.check_items:
            playbook[-1]['tasks'][0]['when'] = self.check_condition
            playbook[-1]['tasks'][1]['when'] = self.check_condition

        if self.write:
            yaml_write(PLAYBOOK_DIR, self.task_id + '.yml', playbook)

        return playbook
