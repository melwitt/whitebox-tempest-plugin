# Copyright 2016
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

from oslo_config import cfg
from oslo_config import types


general_group = cfg.OptGroup(
    name='whitebox',
    title='General Whitebox Tempest plugin config options')

general_opts = [
    cfg.StrOpt(
        'nodes_yaml',
        help='File path to the yaml description file of the compute hosts '),
    cfg.StrOpt(
        'ctlplane_ssh_username',
        help='Username to use when accessing controllers and/or compute hosts '
             'over SSH.',
        default='heat-admin',
        deprecated_opts=[cfg.DeprecatedOpt('target_ssh_user',
                                           group='whitebox')]),
    cfg.StrOpt(
        'ctlplane_ssh_private_key_path',
        help='Path to the private key to use when accessing controllers '
             'and/or compute hosts over SSH.',
        default='/home/stack/.ssh/id_rsa',
        deprecated_opts=[cfg.DeprecatedOpt('target_private_key_path',
                                           group='whitebox')]),
    cfg.BoolOpt(
        'containers',
        default=False,
        help='Deployment is containerized.'),
    cfg.DictOpt(
        'ctlplane_addresses',
        help="Dictionary of control plane addresses. The keys are the "
             "compute hostnames as they appear in the OS-EXT-SRV-ATTR:host "
             "field of Nova's show server details API. The values are the "
             "control plane addresses. For example:"
             ""
             "  ctlplane_addresses = compute-0.localdomain:172.16.42.11,"
             "                        compute-1.localdomain:172.16.42.10"
             ""
             "While this looks like a poor man's DNS, this is needed "
             "because the environment running the test does not necessarily "
             "have the ctlplane DNS accessible.",
        deprecated_opts=[cfg.DeprecatedOpt('hypervisors',
                                           group='whitebox')]),
    cfg.IntOpt(
        'max_compute_nodes',
        default=31337,
        help="Number of compute hosts in the deployment. Some tests depend "
             "on there being a single compute host."),
    cfg.IntOpt(
        'available_cinder_storage',
        default=0,
        help="Cinder storage available to the deployment (in GB)."),
    cfg.StrOpt(
        'container_runtime',
        default="docker",
        choices=["docker", "podman"],
        help="Name of the executable running containers. Correct values are"
        " 'docker' (default) for osp 12 to 14, and 'podman' starting 15"),
    cfg.IntOpt(
        'file_backed_memory_size',
        default=0,
        help="file_backed_memory size in mb used to set the"
             " [libvirt]/file_backed_memory in nova.conf"),
    cfg.StrOpt(
        'selinux_label',
        default=None,
        help='provide the selinux labels used by the instance'),
    cfg.StrOpt(
        'selinux_imagelabel',
        default=None,
        help='provide the selinux image labels used by the instance'),
    cfg.IntOpt(
        'flavor_volume_size',
        default=1,
        help="volume size for flavor used in whitebox test"),
    cfg.IntOpt(
        'flavor_ram_size',
        default=64,
        help='Default ram size to use when creating guest flavor'),
    cfg.StrOpt(
        'cpu_model',
        help='The CPU model set in the [libvirt]/cpu_models config option '
             'on the compute hosts. While Nova supports multiple cpu_models '
             '(and has deprecated the old singular [libvirt]/cpu_model '
             'option), whitebox assumes a single CPU model.'),
    cfg.ListOpt(
        'cpu_model_extra_flags',
        help='Extra flags set in the [libvirt]/cpu_model_extra_flags config '
             'option on the compute hosts.'),
    cfg.StrOpt(
        'pmem_flavor_size',
        default=None,
        help='The PMEM mapping to the nvdimm namespaces, this value is passed '
             'as an extra spec during flavor creation to allow for nvdimm '
             'enabled guest creation.  Example mappings include 2GB, 6GB, '
             'MEDIUM, LARGE'),
    cfg.StrOpt(
        'pmem_expected_size',
        default=None,
        help='The expected pmem size allocated to the instance. It requires '
             'an IEC supported unit of measurement, i.e. Kb, Mb, KB, GB, KiB, '
             'GiB, etc. Example format 1GB, 4GiB, 100GB. '),
    cfg.IntOpt(
        'rx_queue_size',
        help='The queue size set in the [libvirt]/rx_queue_size config option '
             'on the compute hosts.'),
    cfg.StrOpt(
        'default_video_model',
        default=None,
        help='The expected default video display for the guest'),
    cfg.IntOpt(
        'max_disk_devices_to_attach',
        default=None,
        help='Maximum number of disks allowed to attach to a singler server'),
    cfg.StrOpt(
        'libvirt_hw_machine_type',
        default='pc',
        choices=["pc", "q35"],
        help='The machine type configured for the nova computes'),
    cfg.IntOpt(
        'hugepage_guest_ram_size',
        default=64,
        help="RAM size in MB to use when launching the guests backed "
             "by hugepages."),
]

nova_compute_group = cfg.OptGroup(
    name='whitebox-nova-compute',
    title='Config options to manage the nova-compute service')

nova_compute_opts = [
    cfg.StrOpt(
        'log_query_command',
        default="journalctl",
        choices=["journalctl", "zgrep"],
        help="Name of the utility to run LogParserClient commands. "
             "Currently, supported values are 'journalctl' (default) "
             "for devstack and 'zgrep' for TripleO"),
    cfg.StrOpt(
        'state_path',
        default="/var/lib/nova",
        help='The [DEFAULT]state_path passed to nova-compute. '
             'Defaults to the default of nova'),
]

database_group = cfg.OptGroup(
    name='whitebox-database',
    title='Config options to access the database.')

database_opts = [
    cfg.StrOpt(
        'host',
        help='Address of the database host. This is normally a controller.'),
    cfg.StrOpt(
        'internal_ip',
        help='If the database service is listening on separate internal '
             'network, this option specifies its IP on that network. It will '
             'be used to set up an SSH tunnel through the database host.'),
    cfg.StrOpt(
        'user',
        help='Username to use when connecting to the database server. '
             'This should normally be the root user, as it needs to '
             'have permissions on all databases.'),
    cfg.StrOpt(
        'password',
        help='The password to use when connecting to the database server.'),
    cfg.StrOpt(
        'nova_cell1_db_name',
        default="nova_cell1",
        help="Name of the Nova db to use for connection"),
    cfg.IntOpt(
        'ssh_gateway_port',
        default=3306,
        help="SSH port forwarding gateway number")
]

hardware_group = cfg.OptGroup(
    name='whitebox-hardware',
    title='Config options that describe the underlying compute node hardware '
          'in the environment.')

hardware_opts = [
    cfg.StrOpt(
        'vgpu_vendor_id',
        default=None,
        help='The vendor id of the underlying vgpu hardware of the compute. '
             'An example with Nvidia would be 10de'),
    cfg.StrOpt(
        'sriov_nic_vendor_id',
        default=None,
        help='The vendor id of the underlying sriov nic port of the compute. '
             'An example with Intel would be 8086'),
    cfg.StrOpt(
        'sriov_vf_product_id',
        default=None,
        help='The product/device id of the underlying sriov VF port for the '
             'NIC. An example with Intel would be 154c'),
    cfg.StrOpt(
        'sriov_pf_product_id',
        default=None,
        help='The product/device id of the underlying sriov PF port of the '
             'NIC. An example with Intel would be 1572'),
    cfg.StrOpt(
        'macvtap_virtio_vendor_id',
        default=None,
        help='The vendor id of the virtio interface device'),
    cfg.StrOpt(
        'macvtap_virtio_product_id',
        default=None,
        help='The product id of the virtio interface device'),
    cfg.ListOpt(
        'smt_hosts',
        default=[],
        help='List of compute hosts that have SMT (Hyper-Threading in Intel '
             'parlance).'),
    cfg.Opt(
        'cpu_topology',
        type=types.Dict(types.List(types.Integer(), bounds=True)),
        help='Host CPU topology, as a dictionary of <NUMA node ID>:'
             '<List of CPUs in that node>. For example, if NUMA node 0 has '
             'CPUs 0 and 1, and NUMA node 1 has CPUs 2 and 3, the value to '
             'set would be `0: [0,1], 1: [2, 3]`.'),
    cfg.Opt(
        'configured_hugepage_sizes',
        type=types.List(types.Integer()),
        default=[],
        help='List of configured hugepage sizes available in kB in the '
             'environment e.g. 2048,1048576'),
    cfg.IntOpt(
        'dedicated_cpus_per_numa',
        default=0,
        help='Number of pCPUs allocated for cpu_dedicated_set per NUMA'),
    cfg.IntOpt(
        'shared_cpus_per_numa',
        default=0,
        help='Number of pCPUs allocated for cpu_shared_set per NUMA'),
    cfg.StrOpt(
        'realtime_mask',
        default=None,
        help='CPU mask used when configuring hw:cpu_realtime_mask'),
    cfg.StrOpt(
        'sriov_physnet',
        default=None,
        help='The physnet to use when creating sr-iov ports'),
    cfg.StrOpt(
        'sriov_vnic_type',
        default=None,
        choices=[None, "direct", "macvtap", "direct-physical"],
        help='SR-IOV vnic type to use when creating port'),
    cfg.IntOpt(
        'sriov_vlan_id',
        default=None,
        help='The vlan id associated with the sriov port'),
    cfg.StrOpt(
        'vdpa_physnet',
        default=None,
        help='The physnet to use when creating vdpa ports'),
    cfg.IntOpt(
        'vdpa_vlan_id',
        default=None,
        help='The vlan id associated with the vdpa port'),
    cfg.IntOpt(
        'physnet_numa_affinity',
        default=None,
        help="The NUMA Node ID that has affinity to the NIC connected to the "
             "physnet defined in 'sriov_physnet'"),
    cfg.DictOpt(
        'vgpu_type_mapping',
        default=None,
        help='Dictionary mapping of the vGPU custom traits to the unique '
             'subsystem id that corresponds with the vGPU device e.g. '
             'CUSTOM_NVIDIA_11:nvidia-319,CUSTOM_NVIDIA_12:nvidia-320'),
    cfg.IntOpt(
        'socket_affinity',
        default=None,
        help="The socket ID that has affinity to the NIC connected to the "
             "physnet defined in 'sriov_physnet'"),
    cfg.Opt(
        'socket_topology',
        default=None,
        type=types.Dict(types.List(types.Integer(), bounds=True)),
        help='Host Socket topology, as a dictionary of <Socket ID>:'
             '<List of NUMA node IDs>. For example, if Socket 0 has '
             'NUMA nodes 0 and 1, and Socket 1 NUMA nodes 2 and 3, the value '
             'to set would be `0: [0,1], 1: [2, 3]`.')
]

compute_features_group_opts = [
    cfg.BoolOpt('virtio_rng',
                default=False,
                help="If false, skip virtio rng tests"),
    cfg.BoolOpt('rbd_download',
                default=False,
                help="If false, skip rbd direct download tests"),
    cfg.BoolOpt('sriov_hotplug',
                default=True,
                help="Sriov hotplugging is supported in the deployment"),
    cfg.BoolOpt('supports_image_level_numa_affinity',
                default=True,
                help="Deployment supports SR-IOV NUMA affinity policy "
                "scheduling base on image properties"),
    cfg.BoolOpt('supports_port_level_numa_affinity',
                default=True,
                help="Deployment supports port level configuration of "
                "NUMA affinity policy for SR-IOV NIC's"),
    cfg.BoolOpt('uefi_boot',
                default=True,
                help="If false, skip standard uefi boot tests"),
    cfg.BoolOpt('uefi_secure_boot',
                default=False,
                help="If false, skip uefi secure boot tests"),
    cfg.BoolOpt('vtpm_device_supported',
                default=False,
                help='vTPM device support for guest instances to store '
                     'secrets. Requires these flags set in nova.conf'
                     '[libvirt]/swtpm_enabled=True'
                     '[libvirt]/swtpm_user=tss'
                     '[libvirt]/swtpm_group=tss'
                     '[key_manager]/backend=barbican'),
    cfg.BoolOpt('vdpa_cold_migration_supported',
                default=False,
                help='Cold migration and resize supported for guest instances '
                'with vDPA ports'),
    cfg.BoolOpt('vgpu_cold_migration_supported',
                default=False,
                help='Cold migration and resize supported for guest instances '
                'with vGPU devices'),
    cfg.BoolOpt('stable_compute_uuid_supported',
                default=False,
                help='Stable compute UUID feature is supported for the '
                     'deployment. This feature is available since 2023.1 '
                     '(Antelope) upstream. If the deployment does not use the '
                     'default value of [DEFAULT]state_path in the nova-compute'
                     'config, then [whitebox-nova-compute]state_path also '
                     'needs to be configured'),
    cfg.BoolOpt('bochs_display_support',
                default=False,
                help="Guests support bochs display device"),
    cfg.BoolOpt('cpu_power_management',
                default=False,
                help="Libvirt CPU power management is turned on."),
    cfg.BoolOpt('vencrypt',
                default=True,
                help="verify vnc console tls."),
    cfg.BoolOpt('image_multibackend',
                default=False,
                help='Multiple image backends are supported in the '
                     'deployment'),
]
