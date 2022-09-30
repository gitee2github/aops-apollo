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
Description:
"""
from apollo.function.cache import LRUCache


class TaskCache(LRUCache):
    """
    A task cache based on LRU, offers some function to transfer host info to certain format
    in addtion to cache.
    """
    @staticmethod
    def make_cve_info(info):
        """
        Transfer original cve task info to certain format.

        Args:
            info (list): cve and host info, e.g.
                [
                    {
                        "cve_id": "id1",
                        "host_info": [
                            {
                                "host_name": "name1",
                                "host_id": "id1",
                                "host_ip": "ip1"
                            }
                        ]
                    }
                ]

        Returns:
            dict: info for task, e.g.
                {
                    "cve": {
                        "id1": 1,
                    },
                    "host": {
                        "name1": {
                            "host_name": "name1",
                            "host_id": "id1",
                            "host_ip": "ip1",
                            "cve": {
                                "id1": 1
                            }
                        }
                    }
                }
        """
        result = {"cve": {}, "host": {}}
        for item in info:
            cve_id = item.get('cve_id')
            result["cve"][cve_id] = 1
            host_info = item.get('host_info')
            for host in host_info:
                host_name = host.get('host_name')
                if host_name in result['host'].keys():
                    result["host"][host_name]["cve"][cve_id] = 1
                else:
                    result["host"][host_name] = host
                    result['host'][host_name]["cve"] = {cve_id: 1}
        return result

    @staticmethod
    def make_host_info(info):
        """
        Transfer host info to a dict of which key is the hostname

        Args:
            info (list): host info, e.g.
                [
                    {
                        "host_name": "name1",
                        "host_ip": "ip1",
                        "host_id": "id1",
                        "repo_name": "name1"
                    }
                ]

        Returns:
            dict: transferred info, e.g.
                {
                    "name1": {
                        "host_name": "name1",
                        "host_id": "id1",
                        "host_ip": "ip1",
                        "repo_name": "name1"
                    }
                }
        """
        result = {}
        for host_info in info:
            host_name = host_info.get('host_name')
            result[host_name] = host_info

        return result

    def query_repo_info(self, task_id, repo_info):
        """
        Get the host info from cache or make the cache when it's not in cache.

        Args:
            task_id (str)
            repo_info (dict)

        Returns:
            dict
        """
        task_info = self.get(task_id)
        # when the cache is missed, query it and add it to cache.
        if task_info is None:
            info = repo_info['result']
            task_info = self.make_host_info(info)
            self.put(task_id, task_info)

        return task_info


# for task about cve fixing, cve rollbacking and repo setting,
# these tasks may be executed frequently.
TASK_CACHE = TaskCache(100)
