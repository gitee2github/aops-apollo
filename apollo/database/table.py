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
Description: mysql tables
"""
from sqlalchemy import Column, ForeignKey
from sqlalchemy.sql.sqltypes import Boolean, Integer, String
from vulcanus.database.table import Base, MyBase
from vulcanus.database.helper import create_tables
from apollo.database import ENGINE


class CveHostAssociation(Base, MyBase):
    """
    cve and vulnerability_host tables' association table, record the cve and host matching
    relationship for fixing cve task
    """
    __tablename__ = "cve_host_match"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cve_id = Column(String(20))
    host_id = Column(Integer, ForeignKey(
        'host.host_id', ondelete="CASCADE"), index=True)
    affected = Column(Boolean)
    fixed = Column(Boolean)
    support_hp = Column(Boolean, default=None)
    fixed_by_hp = Column(Boolean, default=None)


class CveAffectedPkgs(Base, MyBase):
    """
    record the affected packages of cves. A cve may affect multiple packages.
    """
    __tablename__ = "cve_affected_pkgs"

    cve_id = Column(String(20), ForeignKey('cve.cve_id'), primary_key=True)
    package = Column(String(40), primary_key=True)
    package_version = Column(String(50), primary_key=True)
    os_version = Column(String(50), primary_key=True, index=True)
    affected = Column(Integer)


class CveTaskAssociation(Base, MyBase):
    """
    cve and task tables' association table, record cve info
    """
    __tablename__ = "cve_task"

    cve_id = Column(String(20), primary_key=True)
    task_id = Column(String(32), ForeignKey(
        'vul_task.task_id', ondelete="CASCADE"), primary_key=True)
    reboot = Column(Boolean)
    progress = Column(Integer, default=0)
    host_num = Column(Integer, nullable=False)


class TaskCveHostAssociation(Base, MyBase):
    """
    cve, task and host tables' association table, record cve, host and task's matching
    relationship for fixing cve task
    """
    __tablename__ = "task_cve_host"

    task_id = Column(String(32), ForeignKey(
        'vul_task.task_id', ondelete="CASCADE"), primary_key=True)
    cve_id = Column(String(20), primary_key=True)
    host_id = Column(Integer, primary_key=True)
    host_name = Column(String(20), nullable=False)
    host_ip = Column(String(16), nullable=False)
    # status can be "unfixed", "fixed" and "running"
    status = Column(String(20), nullable=False)
    hotpatch = Column(Boolean)


class TaskHostRepoAssociation(Base, MyBase):
    """
    task, host and repo tables' association table, record repo, host and task's matching
    relationship for setting repo task
    """
    __tablename__ = "task_host_repo"

    task_id = Column(String(32), ForeignKey(
        'vul_task.task_id', ondelete="CASCADE"), primary_key=True)
    host_id = Column(Integer, primary_key=True)
    host_name = Column(String(20), nullable=False)
    host_ip = Column(String(16), nullable=False)
    repo_name = Column(String(20), nullable=False)
    # status can be "unset", "set" and "running"
    status = Column(String(20))


class Cve(Base, MyBase):
    """
    Cve table
    """
    __tablename__ = "cve"

    cve_id = Column(String(20), nullable=False, primary_key=True)
    publish_time = Column(String(20))
    severity = Column(String(20))
    cvss_score = Column(String(20))
    reboot = Column(Boolean)


class Repo(Base, MyBase):
    """
    Repo Table
    """
    __tablename__ = "repo"

    repo_id = Column(Integer, autoincrement=True, primary_key=True)
    repo_name = Column(String(20), nullable=False)
    repo_attr = Column(String(20), nullable=False)
    repo_data = Column(String(512), nullable=False)

    username = Column(String(40), ForeignKey('user.username'))


class Task(Base, MyBase):
    """
    Task info Table
    """
    __tablename__ = "vul_task"

    task_id = Column(String(32), primary_key=True, nullable=False)
    task_type = Column(String(10), nullable=False)
    description = Column(String(50), nullable=False)
    task_name = Column(String(20), nullable=False)
    latest_execute_time = Column(Integer)
    need_reboot = Column(Integer)
    auto_reboot = Column(Boolean, default=False)
    create_time = Column(Integer)
    host_num = Column(Integer)
    check_items = Column(String(32))

    username = Column(String(40), ForeignKey('user.username'))


class AdvisoryDownloadRecord(Base, MyBase):
    """
    Download and parse advisory's record
    """
    __tablename__ = "parse_advisory_record"
    id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    advisory_year = Column(String(4), nullable=False)
    advisory_serial_number = Column(String(10), nullable=False)
    download_status = Column(Boolean)


def create_vul_tables(engine=ENGINE):
    """
    create vulnerability tables of apollo service
    Args:
        engine: mysql engine

    Returns:

    """
    # pay attention, the sequence of list is important. Base table need to be listed first.
    tables = [Cve, CveHostAssociation, Task, Repo, AdvisoryDownloadRecord,
              CveTaskAssociation, TaskHostRepoAssociation, TaskCveHostAssociation, CveAffectedPkgs]
    tables_objects = [Base.metadata.tables[table.__tablename__]
                      for table in tables]
    create_tables(Base, engine, tables=tables_objects)
