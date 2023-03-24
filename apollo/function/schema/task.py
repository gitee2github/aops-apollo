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
Description: For task related restful interfaces schema
"""
from marshmallow import Schema
from marshmallow import fields
from marshmallow import validate


class TaskListFilterSchema(Schema):
    """
    filter schema of task list getting interface
    """
    task_name = fields.String(required=False, validate=lambda s: len(s) > 0)
    task_type = fields.List(fields.String(
        validate=validate.OneOf(["cve fix", "repo set"])), required=False)


class GetTaskListSchema(Schema):
    """
    validators for parameter of /vulnerability/task/list/get
    """
    sort = fields.String(required=False, validate=validate.OneOf(
        ["host_num", "create_time"]))
    direction = fields.String(required=False, validate=validate.OneOf(
        ["asc", "desc"]))
    page = fields.Integer(required=False, validate=lambda s: s > 0)
    per_page = fields.Integer(required=False, validate=lambda s: 0 < s < 50)
    filter = fields.Nested(TaskListFilterSchema, required=False)


class GetTaskProgressSchema(Schema):
    """
    validators for parameter of /vulnerability/task/progress/get
    """
    task_list = fields.List(fields.String(), required=True)


class GetTaskInfoSchema(Schema):
    """
    validators for parameter of /vulnerability/task/info/get
    """
    task_id = fields.String(required=True, validate=lambda s: len(s) != 0)


class CveHostInfoDictSchema(Schema):
    """
    single host's info of a cve from
    """
    host_id = fields.Integer(required=True, validate=lambda s: s > 0)
    host_name = fields.String(
        required=True, validate=lambda s:  0 < len(s) <= 20)
    host_ip = fields.IP(required=True)


class CveHostInfoHotpathSchema(CveHostInfoDictSchema):
    """
    single host's info of a cve from /vulnerability/task/cve/generate
    """
    hotpatch = fields.Boolean(required=True)


class CveInfoDictSchema(Schema):
    """
    single cve's info of cve task from /vulnerability/task/cve/generate
    """
    cve_id = fields.String(required=True, validate=lambda s: len(s) != 0)
    host_info = fields.List(fields.Nested(CveHostInfoHotpathSchema), required=True,
                            validate=lambda s: len(s) > 0)
    reboot = fields.Boolean(required=True)


class GenerateCveTaskSchema(Schema):
    """
    validators for parameter of /vulnerability/task/cve/generate
    """
    task_name = fields.String(required=True, validate=lambda s: len(s) != 0)
    description = fields.String(
        required=True, validate=lambda s: 0 < len(s) <= 50)
    auto_reboot = fields.Boolean(required=False, default=True)
    check_items = fields.String(
        required=False, validate=lambda s: 0 < len(s) <= 32)
    info = fields.List(fields.Nested(CveInfoDictSchema), required=True,
                       validate=lambda s: len(s) > 0)


class CveTaskInfoFilterSchema(Schema):
    """
    filter schema of cve task info getting interface
    """
    cve_id = fields.String(required=False, validate=lambda s: len(s) > 0)
    reboot = fields.Boolean(required=False)
    status = fields.List(fields.String(
        validate=validate.OneOf(["succeed", "fail", "running", "unknown"])),
        required=False)


class GetCveTaskInfoSchema(Schema):
    """
    validators for parameter of /vulnerability/task/cve/info/get
    """
    task_id = fields.String(required=True, validate=lambda s: len(s) != 0)
    sort = fields.String(required=False, validate=validate.OneOf(
        ["host_num"]))
    direction = fields.String(required=False, validate=validate.OneOf(
        ["asc", "desc"]))
    page = fields.Integer(required=False, validate=lambda s: s > 0)
    per_page = fields.Integer(required=False, validate=lambda s: 0 < s < 50)
    filter = fields.Nested(CveTaskInfoFilterSchema, required=False)


class GetCveTaskStatusSchema(Schema):
    """
    validators for parameter of /vulnerability/task/cve/status/get
    """
    task_id = fields.String(required=True, validate=lambda s: len(s) != 0)
    cve_list = fields.List(fields.String(), required=True)


class GetCveTaskProgressSchema(Schema):
    """
    validators for parameter of /vulnerability/task/cve/progress/get
    """
    task_id = fields.String(required=True, validate=lambda s: len(s) != 0)
    cve_list = fields.List(fields.String(), required=True)


class GetCveTaskResultSchema(Schema):
    """
    validators for parameter of /vulnerability/task/cve/result/get
    """
    task_id = fields.String(required=True, validate=lambda s: len(s) != 0)
    cve_list = fields.List(fields.String(), required=True)


class RollbackCveTaskSchema(Schema):
    """
    validators for parameter of /vulnerability/task/cve/rollback
    """
    task_id = fields.String(required=True, validate=lambda s: len(s) != 0)
    cve_list = fields.List(fields.String(), required=True)


class GenerateRepoTaskSchema(Schema):
    """
    validators for parameter of /vulnerability/task/repo/generate
    """
    task_name = fields.String(
        required=True, validate=lambda s: 0 < len(s) <= 20)
    description = fields.String(
        required=True, validate=lambda s: 0 < len(s) <= 50)
    repo_name = fields.String(
        required=True, validate=lambda s: 0 < len(s) <= 20)
    info = fields.List(fields.Nested(CveHostInfoDictSchema), required=True,
                       validate=lambda s: len(s) > 0)


class RepoTaskInfoFilterSchema(Schema):
    """
    filter schema of repo task info getting interface
    """
    host_name = fields.String(required=False, validate=lambda s: len(s) > 0)
    status = fields.List(fields.String(
        validate=validate.OneOf(["succeed", "fail", "running", "unknown"])),
        required=False)


class GetRepoTaskInfoSchema(Schema):
    """
    validators for parameter of /vulnerability/task/repo/info/get
    """
    task_id = fields.String(required=True, validate=lambda s: len(s) != 0)
    page = fields.Integer(required=False, validate=lambda s: s > 0)
    per_page = fields.Integer(required=False, validate=lambda s: 0 < s < 50)
    filter = fields.Nested(RepoTaskInfoFilterSchema, required=False)


class GetRepoTaskResultSchema(Schema):
    """
    validators for parameter of /vulnerability/task/repo/result/get
    """
    task_id = fields.String(required=True, validate=lambda s: len(s) != 0)
    host_list = fields.List(fields.Integer(
        required=True, validate=lambda s: s > 0), required=True)


class ExecuteTaskSchema(Schema):
    """
    validators for parameter of /vulnerability/task/execute
    """
    task_id = fields.String(required=True, validate=lambda s: len(s) != 0)


class DeleteTaskSchema(Schema):
    """
    validators for parameter of /vulnerability/task/delete
    """
    task_list = fields.List(fields.String(), required=True,
                            validate=lambda s: len(s) != 0)


class CveFixCallbackSchema(Schema):
    task_id = fields.String(required=True, validate=lambda s: len(s) != 0)
    host_id = fields.Integer(required=True, validate=lambda s: s > 0)
    cves = fields.Dict(keys=fields.Str(), values=fields.Str())


class RepoSetCallbackSchema(Schema):
    task_id = fields.String(required=True, validate=lambda s: len(s) != 0)
    host_id = fields.Integer(required=True, validate=lambda s: s > 0)
    status = fields.String(required=True, validate=lambda s: len(s) != 0)
    repo_name = fields.String(required=True, validate=lambda s: len(s) != 0)


class CveHostPatchInfoSchema(Schema):
    cve_id = fields.String(required=True, validate=lambda s: len(s) != 0)
    hotpatch = fields.Boolean()


class InstallPcakageInfoSchema(Schema):
    name = fields.String(required=True, validate=lambda s: len(s) != 0)
    version = fields.String(required=True, validate=lambda s: len(s) != 0)


class CveScanCallbackSchema(Schema):
    task_id = fields.String(required=True, validate=lambda s: len(s) != 0)
    host_id = fields.Integer(required=True, validate=lambda s: s > 0)
    status = fields.String(required=True, validate=lambda s: len(s) != 0)
    installed_packages = fields.List(fields.Nested(
        InstallPcakageInfoSchema(), required=True), required=True)
    os_version = fields.String(required=True)
    cves = fields.List(fields.Nested(
        CveHostPatchInfoSchema(), required=True), required=True)


__all__ = [
    'GetTaskListSchema',
    'GetTaskProgressSchema',
    'GetTaskInfoSchema',
    'GenerateCveTaskSchema',
    'GetCveTaskInfoSchema',
    'GetCveTaskStatusSchema',
    'GetCveTaskProgressSchema',
    'GetCveTaskResultSchema',
    'RollbackCveTaskSchema',
    'GenerateRepoTaskSchema',
    'GetRepoTaskInfoSchema',
    'GetRepoTaskResultSchema',
    'ExecuteTaskSchema',
    'DeleteTaskSchema',
    'CveFixCallbackSchema',
    'RepoSetCallbackSchema',
    'CveScanCallbackSchema'
]
