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

from oslo_log import log as logging
from tempest import config

from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.services.clients import QEMUImgClient

CONF = config.CONF
LOG = logging.getLogger(__name__)


# TODO(lyarwood): Use a non admin base class in order to allow the encrypted
# volume and secrets to be created by a non-admin user.
class TestImageMultiBackend(base.BaseWhiteboxComputeTest):
    '''Test which validates encryption. The test performs the following:

    1. Create a VM
    2. Create two volumes- encrypted and unencrypted
    3. Attach both volumes to the VM
    4. Gather all xml disk elements from guest
    5. Search all xml disk elements for the disk containing the encryption
    element and correct serial id
    6. Validate the xml disk's encryption format is luks
    7. Create volume path based on disk type and pass it to qemu-img to get
    detailed information about the volume.
    8. From the returned info confirm the volume is encrypted and the format
    is luks
    '''

    min_microversion = '2.97'

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if not CONF.compute_feature_enabled.image_multibackend::
            raise cls.skipException('Image multibackend is not supported')

    def test_different_image_backend_per_disk(self):
        flavor = self.create_flavor()
        image_id = self.copy_default_image()

        root_bdm = {
            'uuid': image_id,
            'source_type': 'image',
            'destination_type': 'local',
            'volume_size': 1,
            'boot_index': 0,
            'image_type': 'qcow2',
        }
        eph_bdm = {
            'source_type': 'blank',
            'destination_type': 'local',
            'volume_size': 1,
            'boot_index': -1,
            'image_type': 'rbd',
        }
        swap_bdm = {
            'source_type': 'blank',
            'destination_type': 'local',
            'volume_size': 512,
            'boot_index': -1,
            'image_type': 'raw',
            'guest_format': 'swap',
        }

        server = self.create_test_server(
            flavor=flavor['id'],
            block_device_mapping_v2=[root_bdm, eph_bdm, swap_bdm], image_id='',
            wait_until='ACTIVE')

        xml = self.get_server_xml(server['id'])

        attached_disks = xml.findall('.//disk')

        self.assertEqual(3, len(attached_disks))

        host = self.get_host_for_server(server['id'])
        qemu_img_client = QEMUImgClient(host)
        # This works because "device_name" just looks for a pattern in the
        # domblklist output line. The swap disk will be named "disk.swap".
        eph_disk_path = self.get_server_blockdevice_path(
            server['id'], 'eph')
        qemu_info = qemu_img_client.info(swap_disk_path)
        self.assertEqual('raw', qemu_info['format'])

        swap_disk_path = self.get_server_blockdevice_path(
            server['id'], 'swap')
        qemu_info = qemu_img_client.info(swap_disk_path)
        self.assertEqual('raw', qemu_info['format'])

    def test_qemu_volume_encryption(self):
        server = self.create_test_server(wait_until="ACTIVE")
        unencrypted_vol = self.create_volume()
        encrypted_vol = self.create_encrypted_volume(
            'luks',
            volume_type='luks'
        )

        # Attach encrypted and unencrypted volume to the server
        self.attach_volume(server, unencrypted_vol)
        self.attach_volume(server, encrypted_vol)

        # Gather instance XML to ensure the encrypted volume is attached to the
        # instance
        xml = self.get_server_xml(server['id'])

        # Create a list of all attached volumes on the instance
        attached_volumes = xml.findall('.//disk')

        # Search the list of disks for the encrypted volume by matching the
        # disk's serial id with the volume id provided by the volumes client
        # and also query that it contains the 'encryption/secret' elements
        xml_disk_elements = [x for x in attached_volumes if
                             getattr(x.find('./serial'), 'text', None) ==
                             encrypted_vol['id'] and
                             x.find("./encryption/secret") is not None]

        # There should be one and only one disk element present in the
        # instance xml that matches search criteria
        xml_disk_count = len(xml_disk_elements)
        self.assertEqual(
            1, xml_disk_count, 'Expected to find one and only one xml disk '
            'element matching search criteria but instead found %s' %
            xml_disk_count)
        encrypted_disk_xml_element = xml_disk_elements[0]

        # Confirm encryption format is luks
        encryption_format = encrypted_disk_xml_element.find(
            './encryption').get('format')
        self.assertEqual(
            'luks', encryption_format, 'Expected encryption type luks but '
            'found %s' % encryption_format)

        # Determine the encrypted disk's protocol. If RBD then gather user
        # and volume name to generate path, otherwise just use 'source/dev' for
        # volume path
        protocol = encrypted_disk_xml_element.find('./source').get('protocol')
        if protocol and protocol == 'rbd':
            volume = encrypted_disk_xml_element.find('./source').get('name')
            user = encrypted_disk_xml_element.find('./auth').get('username')
            if user:
                path = f"rbd:{volume}:id={user}"
            else:
                path = f"rbd:{volume}"
        else:
            path = encrypted_disk_xml_element.find('./source').get('dev')

        # Get volume details from qemu-img info with the previously generated
        # volume path
        host = self.get_host_for_server(server['id'])
        qemu_img_client = QEMUImgClient(host)
        qemu_info = qemu_img_client.info(path)

        # Check reported qemu-img info that volume is encrypted and the format
        # is luks
        self.assertTrue(
            qemu_info.get('encrypted'), 'qemu-img did not report that the '
            'volume was encrypted')

        qemu_info_encrypt_format = qemu_info.get('format')
        self.assertEqual(
            'luks', qemu_info_encrypt_format, 'Expected volume format to be '
            'luks but instead found %s' % qemu_info_encrypt_format)
