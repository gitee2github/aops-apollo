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
Description: task related configuration, constant
"""
import os

from apollo.conf import configuration

HOST_VAULT_DIR = configuration.apollo.get('HOST_VAULT_DIR')
REPO_DIR = os.path.join(HOST_VAULT_DIR, 'repo')
cve_fix_func = configuration.cve.get("CVE_FIX_FUNCTION")
cve_scan_time = configuration.cve.get("CVE_SCAN_TIME")


CVE_CHECK_ITEMS = [
]


REPO_CHECK_ITEMS = [
]
