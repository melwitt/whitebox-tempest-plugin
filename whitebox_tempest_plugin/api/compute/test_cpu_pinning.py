# Copyright 2015 Intel Corporation
# Copyright 2018 Red Hat Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Tests for CPU pinning and CPU thread pinning policies.

Based on tests for the Intel NFV CI.

For more information, refer to:

- https://wiki.openstack.org/wiki/ThirdPartySystems/Intel_NFV_CI
- https://github.com/openstack/intel-nfv-ci-tests
"""

from itertools import chain
import testtools
import xml.etree.ElementTree as ET

from oslo_serialization import jsonutils
from tempest.common import compute
from tempest.common import utils
from tempest.common import waiters
from tempest import config
from tempest.lib import decorators

from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.services import clients
from whitebox_tempest_plugin import utils as whitebox_utils

from oslo_log import log as logging


CONF = config.CONF
LOG = logging.getLogger(__name__)


class BasePinningTest(base.BaseWhiteboxComputeTest):

    shared_cpu_policy = {'hw:cpu_policy': 'shared'}
    dedicated_cpu_policy = {'hw:cpu_policy': 'dedicated'}

    def get_server_cell_pinning(self, server_id):
        """Get the host NUMA cell numbers to which the server's virtual NUMA
        cells are pinned.

        :param server_id: The instance UUID to look up.
        :return cpu_pins: A dict of guest cell number -> set(host cell numbers
                          said cell is pinned to)
        """
        root = self.get_server_xml(server_id)

        memnodes = root.findall('./numatune/memnode')
        cell_pins = {}
        for memnode in memnodes:
            cell_pins[int(memnode.get('cellid'))] = \
                whitebox_utils.parse_cpu_spec(memnode.get('nodeset'))

        return cell_pins

    def get_server_emulator_threads(self, server_id):
        """Get the host CPU numbers to which the server's emulator threads are
        pinned.

        :param server_id: The instance UUID to look up.
        :return emulator_threads: A set of host CPU numbers.
        """
        root = self.get_server_xml(server_id)

        emulatorpins = root.findall('./cputune/emulatorpin')
        emulator_threads = set()
        for pin in emulatorpins:
            emulator_threads |= \
                whitebox_utils.parse_cpu_spec(pin.get('cpuset'))

        return emulator_threads

    def get_server_cpu_pinning(self, server_id):
        """Get the host CPU numbers to which the server's vCPUs are pinned.
        Assumes that cpu_policy=dedicated is in effect so that every vCPU is
        pinned to a single pCPU.

        :param server_id: The instance UUID to look up.
        :return cpu_pins: A int:int dict indicating CPU pins.
        """
        root = self.get_server_xml(server_id)

        vcpupins = root.findall('./cputune/vcpupin')
        # NOTE(artom) This assumes every guest CPU is pinned to a single host
        # CPU - IOW that the 'dedicated' cpu_policy is in effect.
        cpu_pins = {int(pin.get('vcpu')): int(pin.get('cpuset'))
                    for pin in vcpupins if pin is not None}

        return cpu_pins

    def _get_db_numa_topology(self, instance_uuid):
        """Returns an instance's NUMA topology as a JSON object.
        """
        db_client = clients.DatabaseClient()
        db = CONF.whitebox_database.nova_cell1_db_name
        with db_client.cursor(db) as cursor:
            cursor.execute('SELECT numa_topology FROM instance_extra '
                           'WHERE instance_uuid = "%s"' % instance_uuid)
            numa_topology = jsonutils.loads(
                cursor.fetchone()['numa_topology'])
            numa_topology = whitebox_utils.normalize_json(numa_topology)
        return numa_topology


class CPUPolicyTest(BasePinningTest):
    """Validate CPU policy support."""
    vcpus = 2

    @classmethod
    def skip_checks(cls):
        super(CPUPolicyTest, cls).skip_checks()
        if not utils.is_extension_enabled('OS-FLV-EXT-DATA', 'compute'):
            msg = "OS-FLV-EXT-DATA extension not enabled."
            raise cls.skipException(msg)

    def test_cpu_shared(self):
        """Ensure an instance with an explicit 'shared' policy work."""
        flavor = self.create_flavor(vcpus=self.vcpus,
                                    extra_specs=self.shared_cpu_policy)
        self.create_test_server(flavor=flavor['id'])

    @testtools.skipUnless(CONF.whitebox.max_compute_nodes < 2,
                          'Single compute node required.')
    def test_cpu_dedicated(self):
        """Ensure an instance with 'dedicated' pinning policy work.

        This is implicitly testing the 'prefer' policy, given that that's the
        default. However, we check specifics of that later and only assert that
        things aren't overlapping here.
        """
        flavor = self.create_flavor(vcpus=self.vcpus,
                                    extra_specs=self.dedicated_cpu_policy)
        server_a = self.create_test_server(flavor=flavor['id'])
        server_b = self.create_test_server(flavor=flavor['id'])
        cpu_pinnings_a = self.get_server_cpu_pinning(server_a['id'])
        cpu_pinnings_b = self.get_server_cpu_pinning(server_b['id'])

        self.assertEqual(
            len(cpu_pinnings_a), self.vcpus,
            "Instance should be pinned but it is unpinned")
        self.assertEqual(
            len(cpu_pinnings_b), self.vcpus,
            "Instance should be pinned but it is unpinned")

        self.assertTrue(
            set(cpu_pinnings_a.values()).isdisjoint(
                set(cpu_pinnings_b.values())),
            "Unexpected overlap in CPU pinning: {}; {}".format(
                cpu_pinnings_a,
                cpu_pinnings_b))

    @testtools.skipUnless(CONF.compute_feature_enabled.resize,
                          'Resize not available.')
    def test_resize_pinned_server_to_unpinned(self):
        """Ensure resizing an instance to unpinned actually drops pinning."""
        flavor_a = self.create_flavor(vcpus=self.vcpus,
                                      extra_specs=self.dedicated_cpu_policy)
        server = self.create_test_server(flavor=flavor_a['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server['id'])

        self.assertEqual(
            len(cpu_pinnings), self.vcpus,
            "Instance should be pinned but is unpinned")

        flavor_b = self.create_flavor(vcpus=self.vcpus,
                                      extra_specs=self.shared_cpu_policy)
        server = self.resize_server(server['id'], flavor_b['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server['id'])

        self.assertEqual(
            len(cpu_pinnings), 0,
            "Resized instance should be unpinned but is still pinned")

    @testtools.skipUnless(CONF.compute_feature_enabled.resize,
                          'Resize not available.')
    def test_resize_unpinned_server_to_pinned(self):
        """Ensure resizing an instance to pinned actually applies pinning."""
        flavor_a = self.create_flavor(vcpus=self.vcpus,
                                      extra_specs=self.shared_cpu_policy)
        server = self.create_test_server(flavor=flavor_a['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server['id'])

        self.assertEqual(
            len(cpu_pinnings), 0,
            "Instance should be unpinned but is pinned")

        flavor_b = self.create_flavor(vcpus=self.vcpus,
                                      extra_specs=self.dedicated_cpu_policy)
        server = self.resize_server(server['id'], flavor_b['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server['id'])

        self.assertEqual(
            len(cpu_pinnings), self.vcpus,
            "Resized instance should be pinned but is still unpinned")

    def test_reboot_pinned_server(self):
        """Ensure pinning information is persisted after a reboot."""
        flavor = self.create_flavor(vcpus=self.vcpus,
                                    extra_specs=self.dedicated_cpu_policy)
        server = self.create_test_server(flavor=flavor['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server['id'])

        self.assertEqual(
            len(cpu_pinnings), self.vcpus,
            "CPU pinning was not applied to new instance.")

        server = self.reboot_server(server['id'], 'HARD')
        cpu_pinnings = self.get_server_cpu_pinning(server['id'])

        # we don't actually assert that the same pinning information is used
        # because that's not expected. We just care that _some_ pinning is in
        # effect
        self.assertEqual(
            len(cpu_pinnings), self.vcpus,
            "Rebooted instance has lost its pinning information")


class CPUThreadPolicyTest(BasePinningTest):
    """Validate CPU thread policy support."""

    vcpus = 2
    isolate_thread_policy = {'hw:cpu_policy': 'dedicated',
                             'hw:cpu_thread_policy': 'isolate'}
    prefer_thread_policy = {'hw:cpu_policy': 'dedicated',
                            'hw:cpu_thread_policy': 'prefer'}
    require_thread_policy = {'hw:cpu_policy': 'dedicated',
                             'hw:cpu_thread_policy': 'require'}

    @staticmethod
    def get_siblings_list(sib):
        """Parse a list of siblings as used by libvirt.

        List of siblings can consist of comma-separated lists (0,5,6)
        or hyphen-separated ranges (0-3) or both.

        >>> get_siblings_list('0-2,3,4,5-6,9')
        [0, 1, 2, 3, 4, 5, 6, 9]
        """
        siblings = []
        for sub_sib in sib.split(','):
            if '-' in sub_sib:
                start_sib, end_sib = sub_sib.split('-')
                siblings.extend(range(int(start_sib),
                                      int(end_sib) + 1))
            else:
                siblings.append(int(sub_sib))

        return siblings

    def get_host_cpu_siblings(self, host):
        """Return core to sibling mapping of the host CPUs.

            {core_0: [sibling_a, sibling_b, ...],
             core_1: [sibling_a, sibling_b, ...],
             ...}

        `virsh capabilities` is called to get details about the host
        then a list of siblings per CPU is extracted and formatted to single
        level list.
        """
        siblings = {}

        host = whitebox_utils.get_ctlplane_address(host)
        virshxml = clients.VirshXMLClient(host)
        capxml = virshxml.capabilities()
        root = ET.fromstring(capxml)
        cpu_cells = root.findall('./host/topology/cells/cell/cpus')
        for cell in cpu_cells:
            cpus = cell.findall('cpu')
            for cpu in cpus:
                cpu_id = int(cpu.get('id'))
                sib = cpu.get('siblings')
                siblings.update({cpu_id: self.get_siblings_list(sib)})

        return siblings

    def test_threads_isolate(self):
        """Ensure vCPUs *are not* placed on thread siblings."""
        flavor = self.create_flavor(vcpus=self.vcpus,
                                    extra_specs=self.isolate_thread_policy)
        server = self.create_test_server(flavor=flavor['id'])
        host = server['OS-EXT-SRV-ATTR:host']

        cpu_pinnings = self.get_server_cpu_pinning(server['id'])
        pcpu_siblings = self.get_host_cpu_siblings(host)

        self.assertEqual(len(cpu_pinnings), self.vcpus)

        # if the 'isolate' policy is used, then when one thread is used
        # the other should never be used.
        for vcpu in set(cpu_pinnings):
            pcpu = cpu_pinnings[vcpu]
            sib = pcpu_siblings[pcpu]
            sib.remove(pcpu)
            self.assertTrue(
                set(sib).isdisjoint(cpu_pinnings.values()),
                "vCPUs siblings should not have been used")

    @testtools.skipUnless(len(CONF.whitebox_hardware.smt_hosts) > 0,
                          'At least 1 SMT-capable compute host is required')
    def test_threads_prefer(self):
        """Ensure vCPUs *are* placed on thread siblings.

        For this to work, we require a host with HyperThreads. Scheduling will
        pass without this, but the test will not.
        """
        flavor = self.create_flavor(vcpus=self.vcpus,
                                    extra_specs=self.prefer_thread_policy)
        server = self.create_test_server(flavor=flavor['id'])
        host = server['OS-EXT-SRV-ATTR:host']

        cpu_pinnings = self.get_server_cpu_pinning(server['id'])
        pcpu_siblings = self.get_host_cpu_siblings(host)

        self.assertEqual(len(cpu_pinnings), self.vcpus)

        for vcpu in set(cpu_pinnings):
            pcpu = cpu_pinnings[vcpu]
            sib = pcpu_siblings[pcpu]
            sib.remove(pcpu)
            self.assertFalse(
                set(sib).isdisjoint(cpu_pinnings.values()),
                "vCPUs siblings were required by not used. Does this host "
                "have HyperThreading enabled?")

    @testtools.skipUnless(len(CONF.whitebox_hardware.smt_hosts) > 0,
                          'At least 1 SMT-capable compute host is required')
    def test_threads_require(self):
        """Ensure thread siblings are required and used.

        For this to work, we require a host with HyperThreads. Scheduling will
        fail without this.
        """
        flavor = self.create_flavor(vcpus=self.vcpus,
                                    extra_specs=self.require_thread_policy)
        server = self.create_test_server(flavor=flavor['id'])
        host = server['OS-EXT-SRV-ATTR:host']

        cpu_pinnings = self.get_server_cpu_pinning(server['id'])
        pcpu_siblings = self.get_host_cpu_siblings(host)

        self.assertEqual(len(cpu_pinnings), self.vcpus)

        for vcpu in set(cpu_pinnings):
            pcpu = cpu_pinnings[vcpu]
            sib = pcpu_siblings[pcpu]
            sib.remove(pcpu)
            self.assertFalse(
                set(sib).isdisjoint(cpu_pinnings.values()),
                "vCPUs siblings were required and were not used. Does this "
                "host have HyperThreading enabled?")


class NUMALiveMigrationBase(BasePinningTest):

    @classmethod
    def skip_checks(cls):
        super(NUMALiveMigrationBase, cls).skip_checks()
        if (CONF.compute.min_compute_nodes < 2 or
                CONF.whitebox.max_compute_nodes > 2):
            raise cls.skipException('Exactly 2 compute nodes required.')

    def _get_cpu_pins_from_db_topology(self, db_topology):
        """Given a JSON object representing a instance's database NUMA
        topology, returns a dict of dicts indicating CPU pinning, for example:
        {0: {'1': 2, '3': 4},
         1: {'2': 6, '7': 8}}
        """
        pins = {}
        cell_count = 0
        for cell in db_topology['nova_object.data']['cells']:
            pins[cell_count] = cell['nova_object.data']['cpu_pinning_raw']
            cell_count += 1
        return pins

    def _get_pcpus_from_cpu_pins(self, cpu_pins):
        """Given a dict of dicts of CPU pins, return just the host pCPU IDs for
        all cells and guest vCPUs.
        """
        pcpus = set()
        for cell, pins in cpu_pins.items():
            pcpus.update(set(pins.values()))
        return pcpus

    def _get_cpus_per_node(self, *args):
        """Given a list of iterables, each containing the CPU IDs for a
        certain NUMA node, return a set containing the number of CPUs in each
        node. This is only used to make sure all NUMA nodes have the same
        number of CPUs - which cannot happen on real hardware, but could happen
        in virtual machines.
        """
        return set([len(cpu_list) for cpu_list in chain(*args)])

    def _get_shared_cpuset(self, server_id):
        """Search the xml vcpu element of the provided server for its cpuset.
        Convert cpuset found into a set of integers.
        """
        root = self.get_server_xml(server_id)
        cpuset = root.find('./vcpu').attrib.get('cpuset', None)
        return whitebox_utils.parse_cpu_spec(cpuset)


class NUMALiveMigrationTest(NUMALiveMigrationBase):

    # Don't bother with old microversions where disk_over_commit was required
    # for the live migration request.
    min_microversion = '2.25'

    @classmethod
    def skip_checks(cls):
        super(NUMALiveMigrationTest, cls).skip_checks()
        if not compute.is_scheduler_filter_enabled('DifferentHostFilter'):
            raise cls.skipException('DifferentHostFilter required.')

    @decorators.skip_because(bug='2007395', bug_type='storyboard')
    def test_cpu_pinning(self):
        host1, host2 = self.list_compute_hosts()
        ctlplane1, ctlplane2 = [whitebox_utils.get_ctlplane_address(host) for
                                host in [host1, host2]]

        numaclient_1 = clients.NUMAClient(ctlplane1)
        numaclient_2 = clients.NUMAClient(ctlplane2)

        # Get hosts's topology
        topo_1 = numaclient_1.get_host_topology()
        topo_2 = numaclient_2.get_host_topology()

        # Need at least 2 NUMA nodes per host
        if len(topo_1) < 2 or len(topo_2) < 2:
            raise self.skipException('At least 2 NUMA nodes per host required')

        # All NUMA nodes need to have same number of CPUs
        cpus_per_node = self._get_cpus_per_node(topo_1.values(),
                                                topo_2.values())
        if len(cpus_per_node) != 1:
            raise self.skipException('NUMA nodes must have same number of '
                                     'CPUs')

        # Set both hosts's vcpu_pin_set to the CPUs in the first NUMA node to
        # force instances to land there
        host1_sm = clients.NovaServiceManager(host1, 'nova-compute',
                                              self.os_admin.services_client)
        host2_sm = clients.NovaServiceManager(host2, 'nova-compute',
                                              self.os_admin.services_client)
        with whitebox_utils.multicontext(
            host1_sm.config_options(('DEFAULT', 'vcpu_pin_set',
                                     self._get_cpu_spec(topo_1[0]))),
            host2_sm.config_options(('DEFAULT', 'vcpu_pin_set',
                                     self._get_cpu_spec(topo_2[0])))
        ):
            # Boot 2 servers such that their vCPUs "fill" a NUMA node.
            specs = {'hw:cpu_policy': 'dedicated'}
            flavor = self.create_flavor(vcpus=cpus_per_node.pop(),
                                        extra_specs=specs)
            server_a = self.create_test_server(flavor=flavor['id'])
            # TODO(artom) As of 2.68 we can no longer force a live-migration,
            # and having the different_host hint in the RequestSpec will
            # prevent live migration. Start enabling/disabling
            # DifferentHostFilter as needed?
            server_b = self.create_test_server(
                flavor=flavor['id'],
                scheduler_hints={'different_host': server_a['id']})

            # At this point we expect CPU pinning in the database to be
            # identical for both servers
            db_topo_a = self._get_db_numa_topology(server_a['id'])
            db_pins_a = self._get_cpu_pins_from_db_topology(db_topo_a)
            db_topo_b = self._get_db_numa_topology(server_b['id'])
            db_pins_b = self._get_cpu_pins_from_db_topology(db_topo_b)
            self.assertEqual(db_pins_a, db_pins_b,
                             'Expected servers to have identical CPU pins, '
                             'instead have %s and %s' % (db_pins_a,
                                                         db_pins_b))

            # They should have identical (non-null) CPU pins
            pin_a = self.get_pinning_as_set(server_a['id'])
            pin_b = self.get_pinning_as_set(server_b['id'])
            self.assertTrue(pin_a and pin_b,
                            'Pinned servers are actually unpinned: '
                            '%s, %s' % (pin_a, pin_b))
            self.assertEqual(
                pin_a, pin_b,
                'Pins should be identical: %s, %s' % (pin_a, pin_b))

            # Live migrate server_b to server_a's compute, adding the second
            # NUMA node's CPUs to vcpu_pin_set
            host_a = self.get_host_other_than(server_b['id'])
            host_a_addr = whitebox_utils.get_ctlplane_address(host_a)
            host_a_sm = clients.NovaServiceManager(
                host_a, 'nova-compute', self.os_admin.services_client)
            numaclient_a = clients.NUMAClient(host_a_addr)
            topo_a = numaclient_a.get_host_topology()
            with host_a_sm.config_options(
                ('DEFAULT', 'vcpu_pin_set',
                 self._get_cpu_spec(topo_a[0] + topo_a[1]))
            ):
                self.live_migrate(server_b['id'], host_a, 'ACTIVE')

                # They should have disjoint (non-null) CPU pins in their XML
                pin_a = self.get_pinning_as_set(server_a['id'])
                pin_b = self.get_pinning_as_set(server_b['id'])
                self.assertTrue(pin_a and pin_b,
                                'Pinned servers are actually unpinned: '
                                '%s, %s' % (pin_a, pin_b))
                self.assertTrue(pin_a.isdisjoint(pin_b),
                                'Pins overlap: %s, %s' % (pin_a, pin_b))

                # Same for their topologies in the database
                db_topo_a = self._get_db_numa_topology(server_a['id'])
                pcpus_a = self._get_pcpus_from_cpu_pins(
                    self._get_cpu_pins_from_db_topology(db_topo_a))
                db_topo_b = self._get_db_numa_topology(server_b['id'])
                pcpus_b = self._get_pcpus_from_cpu_pins(
                    self._get_cpu_pins_from_db_topology(db_topo_b))
                self.assertTrue(pcpus_a and pcpus_b)
                self.assertTrue(
                    pcpus_a.isdisjoint(pcpus_b),
                    'Expected servers to have disjoint CPU pins in the '
                    'database, instead have %s and %s' % (pcpus_a, pcpus_b))

                # NOTE(artom) At this point we have to manually delete both
                # servers before the config_options() context manager reverts
                # any config changes it made. This is Nova bug 1836945.
                self.delete_server(server_a['id'])
                self.delete_server(server_b['id'])

    def test_emulator_threads(self):
        # Need 4 CPUs on each host
        host1, host2 = self.list_compute_hosts()
        ctlplane1, ctlplane2 = [whitebox_utils.get_ctlplane_address(host) for
                                host in [host1, host2]]

        for host in [ctlplane1, ctlplane2]:
            numaclient = clients.NUMAClient(host)
            num_cpus = numaclient.get_num_cpus()
            if num_cpus < 4:
                raise self.skipException('%s has %d CPUs, need 4',
                                         host,
                                         num_cpus)

        host1_sm = clients.NovaServiceManager(host1, 'nova-compute',
                                              self.os_admin.services_client)
        host2_sm = clients.NovaServiceManager(host2, 'nova-compute',
                                              self.os_admin.services_client)
        with whitebox_utils.multicontext(
            host1_sm.config_options(('DEFAULT', 'vcpu_pin_set', '0,1'),
                                    ('compute', 'cpu_shared_set', '2')),
            host2_sm.config_options(('DEFAULT', 'vcpu_pin_set', '0,1'),
                                    ('compute', 'cpu_shared_set', '3'))
        ):
            # Boot two servers
            specs = {'hw:cpu_policy': 'dedicated',
                     'hw:emulator_threads_policy': 'share'}
            flavor = self.create_flavor(vcpus=1, extra_specs=specs)
            server_a = self.create_test_server(flavor=flavor['id'])
            server_b = self.create_test_server(
                flavor=flavor['id'],
                scheduler_hints={'different_host': server_a['id']})

            # They should have different (non-null) emulator pins
            threads_a = self.get_server_emulator_threads(server_a['id'])
            threads_b = self.get_server_emulator_threads(server_b['id'])
            self.assertTrue(threads_a and threads_b,
                            'Emulator threads should be pinned, are unpinned: '
                            '%s, %s' % (threads_a, threads_b))
            self.assertTrue(threads_a.isdisjoint(threads_b))

            # Live migrate server_b
            compute_a = self.get_host_other_than(server_b['id'])
            self.live_migrate(server_b['id'], compute_a, 'ACTIVE')

            # They should have identical (non-null) emulator pins and disjoint
            # (non-null) CPU pins
            threads_a = self.get_server_emulator_threads(server_a['id'])
            threads_b = self.get_server_emulator_threads(server_b['id'])
            self.assertTrue(threads_a and threads_b,
                            'Emulator threads should be pinned, are unpinned: '
                            '%s, %s' % (threads_a, threads_b))
            self.assertEqual(threads_a, threads_b)
            pin_a = self.get_pinning_as_set(server_a['id'])
            pin_b = self.get_pinning_as_set(server_b['id'])
            self.assertTrue(pin_a and pin_b,
                            'Pinned servers are actually unpinned: '
                            '%s, %s' % (pin_a, pin_b))
            self.assertTrue(pin_a.isdisjoint(pin_b),
                            'Pins overlap: %s, %s' % (pin_a, pin_b))

            # NOTE(artom) At this point we have to manually delete both
            # servers before the config_options() context manager reverts
            # any config changes it made. This is Nova bug 1836945.
            self.delete_server(server_a['id'])
            self.delete_server(server_b['id'])

    def test_hugepages(self):
        host_a, host_b = [whitebox_utils.get_ctlplane_address(host) for host in
                          self.list_compute_hosts()]

        numaclient_a = clients.NUMAClient(host_a)
        numaclient_b = clients.NUMAClient(host_b)

        # Get the first host's topology and hugepages config
        topo_a = numaclient_a.get_host_topology()
        pagesize_a = numaclient_a.get_pagesize()
        pages_a = numaclient_a.get_hugepages()

        # Same for second host
        topo_b = numaclient_b.get_host_topology()
        pagesize_b = numaclient_b.get_pagesize()
        pages_b = numaclient_b.get_hugepages()

        # Need hugepages
        for pages_config in pages_a, pages_b:
            for numa_cell, pages in pages_config.items():
                if pages['total'] == 0:
                    raise self.skipException('Hugepages required')

        # Need at least 2 NUMA nodes per host
        if len(topo_a) < 2 or len(topo_b) < 2:
            raise self.skipException('At least 2 NUMA nodes per host required')

        # The hosts need to have the same pagesize
        if not pagesize_a == pagesize_b:
            raise self.skipException('Hosts must have same pagesize')

        # All NUMA nodes need to have same number of CPUs
        if len(self._get_cpus_per_node(topo_a.values(),
                                       topo_b.values())) != 1:
            raise self.skipException('NUMA nodes must have same number of '
                                     'CPUs')

        # Same idea, but for hugepages total
        pagecounts = chain(pages_a.values(), pages_b.values())
        if not len(set([count['total'] for count in pagecounts])) == 1:
            raise self.skipException('NUMA nodes must have same number of '
                                     'total hugepages')

        # NOTE(jparker) due to the check to validate each NUMA node has the
        # same number of hugepages, the pagecounts iterator becomes empty.
        # 'Resetting' pagecounts to calculate minimum free huge pages
        pagecounts = chain(pages_a.values(), pages_b.values())
        # The smallest available number of hugepages must be bigger than
        # total / 2 to ensure no node can accept more than 1 instance with that
        # many hugepages
        min_free = min([count['free'] for count in pagecounts])
        min_free_required = pages_a[0]['total'] / 2
        if min_free < min_free_required:
            raise self.skipException(
                'Need enough free hugepages to effectively "fill" a NUMA '
                'node. Need: %d. Have: %d' % (min_free_required, min_free))

        # Create a flavor that'll "fill" a NUMA node
        ram = pagesize_a / 1024 * min_free
        specs = {'hw:numa_nodes': '1',
                 'hw:mem_page_size': 'large'}
        flavor = self.create_flavor(vcpus=len(topo_a[0]), ram=ram,
                                    extra_specs=specs)

        # Boot two servers
        server_a = self.create_test_server(flavor=flavor['id'])
        server_b = self.create_test_server(
            flavor=flavor['id'],
            scheduler_hints={'different_host': server_a['id']})

        # We expect them to end up with the same cell pin - specifically, guest
        # cell 0 to host cell 0.
        pin_a = self.get_server_cell_pinning(server_a['id'])
        pin_b = self.get_server_cell_pinning(server_b['id'])
        self.assertTrue(pin_a and pin_b,
                        'Cells not actually pinned: %s, %s' % (pin_a, pin_b))
        self.assertEqual(pin_a, pin_b,
                         'Servers ended up on different host cells. '
                         'This is OK, but is unexpected and the test cannot '
                         'continue. Pins: %s, %s' % (pin_a, pin_b))

        # Live migrate server_b
        compute_a = self.get_host_other_than(server_b['id'])
        self.live_migrate(server_b['id'], compute_a, 'ACTIVE')

        # Their guest NUMA node 0 should be on different host nodes
        pin_a = self.get_server_cell_pinning(server_a['id'])
        pin_b = self.get_server_cell_pinning(server_b['id'])
        self.assertTrue(pin_a[0] and pin_b[0],
                        'Cells not actually pinned: %s, %s' % (pin_a, pin_b))
        self.assertTrue(pin_a[0].isdisjoint(pin_b[0]))


class NUMACPUDedicatedLiveMigrationTest(NUMALiveMigrationBase):

    min_microversion = '2.74'

    @classmethod
    def skip_checks(cls):
        super(NUMACPUDedicatedLiveMigrationTest, cls).skip_checks()
        if getattr(CONF.whitebox_hardware, 'cpu_topology', None) is None:
            msg = "cpu_topology in whitebox-hardware is not present"
            raise cls.skipException(msg)

    def test_collocation_migration(self):
        cpu_list = self.get_all_cpus()
        if len(cpu_list) < 4:
            raise self.skipException('Requires at least 4 pCPUs to run')

        host1, host2 = self.list_compute_hosts()
        flavor_vcpu_size = 1
        # Use the first two cpu ids for host1's dedicated pCPU and host2's
        # shared pCPUs. Use the third and fourth cpu ids for host1's shared set
        # and host2's dedicated set
        host1_dedicated_set = host2_shared_set = cpu_list[:2]
        host2_dedicated_set = host1_shared_set = cpu_list[2:4]

        dedicated_flavor = self.create_flavor(
            vcpus=flavor_vcpu_size,
            extra_specs=self.dedicated_cpu_policy
        )
        shared_flavor = self.create_flavor(vcpus=flavor_vcpu_size)

        host1_sm = clients.NovaServiceManager(host1, 'nova-compute',
                                              self.os_admin.services_client)
        host2_sm = clients.NovaServiceManager(host2, 'nova-compute',
                                              self.os_admin.services_client)

        with whitebox_utils.multicontext(
            host1_sm.config_options(('compute', 'cpu_dedicated_set',
                                     self._get_cpu_spec(host1_dedicated_set)),
                                    ('compute', 'cpu_shared_set',
                                     self._get_cpu_spec(host1_shared_set))
                                    ),
            host2_sm.config_options(('compute', 'cpu_dedicated_set',
                                     self._get_cpu_spec(host2_dedicated_set)),
                                    ('compute', 'cpu_shared_set',
                                     self._get_cpu_spec(host2_shared_set))
                                    )
        ):
            # Create a total of four instances, with each compute host holding
            # a server with a cpu_dedicated policy and a server that will
            # float across the respective host's cpu_shared_set
            dedicated_server_a = self.create_test_server(
                clients=self.os_admin, flavor=dedicated_flavor['id'],
                host=host1
            )
            shared_server_a = self.create_test_server(
                clients=self.os_admin, flavor=shared_flavor['id'],
                host=host1
            )
            dedicated_server_b = self.create_test_server(
                clients=self.os_admin, flavor=dedicated_flavor['id'],
                host=host2
            )
            shared_server_b = self.create_test_server(
                clients=self.os_admin, flavor=shared_flavor['id'],
                host=host2
            )

            # The pinned vCPU's in the domain XML's for dedicated server A and
            # B should map to physical CPU's that are a subset of the
            # cpu_dedicated_set of their respective compute host.
            server_dedicated_cpus_a = self.get_pinning_as_set(
                dedicated_server_a['id']
            )
            self.assertTrue(server_dedicated_cpus_a.issubset(
                            host1_dedicated_set),
                            'Pinned CPU\'s %s of server A %s is not a subset'
                            ' of %s' % (server_dedicated_cpus_a,
                                        dedicated_server_a['id'],
                                        host1_dedicated_set))

            server_dedicated_cpus_b = self.get_pinning_as_set(
                dedicated_server_b['id']
            )
            self.assertTrue(server_dedicated_cpus_b.issubset(
                            host2_dedicated_set),
                            'Pinned CPU\'s %s of server B %s is not a subset'
                            ' of %s' % (server_dedicated_cpus_b,
                                        dedicated_server_b['id'],
                                        host2_dedicated_set))

            # Shared servers A and B should have a cpuset that is equal to
            # their respective host's cpu_shared_set
            server_shared_cpus_a = self._get_shared_cpuset(
                shared_server_a['id']
            )
            self.assertItemsEqual(server_shared_cpus_a,
                                  host1_shared_set,
                                  'Shared CPU Set %s of shared server A %s is '
                                  'not equal to shared set of of %s' %
                                  (server_shared_cpus_a, shared_server_a['id'],
                                   host1_shared_set))

            server_shared_cpus_b = self._get_shared_cpuset(
                shared_server_b['id']
            )
            self.assertItemsEqual(server_shared_cpus_b,
                                  host2_shared_set,
                                  'Shared CPU Set %s of shared server B %s is '
                                  'not equal to shared set of of %s' %
                                  (server_shared_cpus_b, shared_server_b['id'],
                                   host2_shared_set))

            # Live migrate shared server A to the compute node with shared
            # server B. Both servers are using shared vCPU's so migration
            # should be successful
            self.live_migrate(shared_server_a['id'], host2, 'ACTIVE')

            # Validate shared server A now has a shared cpuset that is a equal
            # to it's new host's cpu_shared_set
            # FIXME(jparker) change host1_shared_set to host2_shared_set once
            # Nova bug 1869804 has been addressed
            shared_set_a = self._get_shared_cpuset(shared_server_a['id'])
            self.assertItemsEqual(shared_set_a, host1_shared_set,
                                  'After migration of server %s, shared CPU '
                                  'set %s is not equal to new shared set %s' %
                                  (shared_server_a['id'], shared_set_a,
                                   host1_shared_set))

            # Live migrate dedicated server A to the same host holding
            # dedicated server B. End result should be all 4 servers are on
            # the same host.
            self.live_migrate(dedicated_server_a['id'], host2, 'ACTIVE')

            # Dedicated server A should have a CPU pin set that is a subset of
            # it's new host's cpu_dedicated_set and should not intersect with
            # dedicated server B's CPU pin set or the cpu_shared_set of the
            # host
            dedicated_pin_a = self.get_pinning_as_set(dedicated_server_a['id'])
            dedicated_pin_b = self.get_pinning_as_set(dedicated_server_b['id'])
            self.assertTrue(dedicated_pin_a.issubset(
                            host2_dedicated_set),
                            'Pinned Host CPU\'s %s of server %s is '
                            'not a subset of %s' % (dedicated_pin_a,
                                                    dedicated_server_a['id'],
                                                    host2_dedicated_set))
            self.assertTrue(dedicated_pin_a.isdisjoint(dedicated_pin_b),
                            'Pinned Host CPU\'s %s of server %s overlaps with '
                            '%s' % (dedicated_pin_a,
                                    dedicated_server_a['id'],
                                    dedicated_pin_b))
            self.assertTrue(dedicated_pin_a.isdisjoint(host2_shared_set),
                            'Pinned Host CPU\'s %s of server %s overlaps with '
                            'cpu_shared_set %s' % (dedicated_pin_a,
                                                   dedicated_server_a['id'],
                                                   host2_shared_set))

            # NOTE(jparker) Due to Nova bug 1836945, cleanUp methods will fail
            # to delete servers when nova.conf configurations revert.  Need to
            # manually delete the servers in the test method.
            self.delete_server(dedicated_server_a['id'])
            self.delete_server(dedicated_server_b['id'])
            self.delete_server(shared_server_a['id'])
            self.delete_server(shared_server_b['id'])


class NUMARebuildTest(BasePinningTest):
    """Test in-place rebuild of NUMA instances"""

    vcpus = 2
    prefer_thread_policy = {'hw:cpu_policy': 'dedicated',
                            'hw:cpu_thread_policy': 'prefer'}

    @classmethod
    def skip_checks(cls):
        super(NUMARebuildTest, cls).skip_checks()
        if not compute.is_scheduler_filter_enabled('NUMATopologyFilter'):
            raise cls.skipException('NUMATopologyFilter required.')

    def test_in_place_rebuild(self):
        """This test should pass provided no NUMA topology changes occur.

        Steps:
        1. Create a VM with one image
        2. Rebuild the VM with another image
        3. Check NUMA topology remains same after rebuild
        """
        flavor = self.create_flavor(vcpus=self.vcpus,
                                    extra_specs=self.prefer_thread_policy)
        server = self.create_test_server(flavor=flavor['id'])
        db_topo_orig = self._get_db_numa_topology(server['id'])
        host = server['OS-EXT-SRV-ATTR:host']
        self.servers_client.rebuild_server(server['id'],
                                           self.image_ref_alt)['server']
        waiters.wait_for_server_status(self.servers_client,
                                       server['id'], 'ACTIVE')
        self.assertEqual(host, self.get_host_for_server(server['id']))
        db_topo_rebuilt = self._get_db_numa_topology(server['id'])
        self.assertEqual(db_topo_orig, db_topo_rebuilt,
                         "NUMA topology doesn't match")
