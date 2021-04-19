#!/bin/sh

function configure {
    echo_summary "Configuring whitebox-tempest-plugin options"
    iniset $TEMPEST_CONFIG whitebox ctlplane_ssh_username $STACK_USER
    iniset $TEMPEST_CONFIG whitebox ctlplane_ssh_private_key_path $WHITEBOX_PRIVKEY_PATH

    # This needs to come from Zuul, as devstack itself has no idea how many
    # nodes are in the env
    iniset $TEMPEST_CONFIG whitebox max_compute_nodes $MAX_COMPUTE_NODES
    iniset $TEMPEST_CONFIG whitebox available_cinder_storage $WHITEBOX_AVAILABLE_CINDER_STORAGE
    if [ -n "$SMT_HOSTS" ]; then
        iniset $TEMPEST_CONFIG whitebox-hardware smt_hosts "$SMT_HOSTS"
    fi
    iniset $TEMPEST_CONFIG whitebox file_backed_memory_size $WHITEBOX_FILE_BACKED_MEMORY_SIZE
    iniset $TEMPEST_CONFIG whitebox cpu_model $WHITEBOX_CPU_MODEL
    iniset $TEMPEST_CONFIG whitebox cpu_model_extra_flags $WHITEBOX_CPU_MODEL_EXTRA_FLAGS
    iniset $TEMPEST_CONFIG whitebox rx_queue_size $WHITEBOX_RX_QUEUE_SIZE

    iniset $TEMPEST_CONFIG whitebox-nova-compute config_path "$WHITEBOX_NOVA_COMPUTE_CONFIG_PATH"
    iniset $TEMPEST_CONFIG whitebox-nova-compute stop_command "$WHITEBOX_NOVA_COMPUTE_STOP_COMMAND"
    iniset $TEMPEST_CONFIG whitebox-nova-compute start_command "$WHITEBOX_NOVA_COMPUTE_START_COMMAND"

    iniset $TEMPEST_CONFIG whitebox-libvirt start_command "$WHITEBOX_LIBVIRT_START_COMMAND"
    iniset $TEMPEST_CONFIG whitebox-libvirt stop_command "$WHITEBOX_LIBVIRT_STOP_COMMAND"
    iniset $TEMPEST_CONFIG whitebox-libvirt mask_command "$WHITEBOX_LIBVIRT_MASK_COMMAND"
    iniset $TEMPEST_CONFIG whitebox-libvirt unmask_command "$WHITEBOX_LIBVIRT_UNMASK_COMMAND"

    iniset $TEMPEST_CONFIG whitebox-database user $DATABASE_USER
    iniset $TEMPEST_CONFIG whitebox-database password $DATABASE_PASSWORD
    iniset $TEMPEST_CONFIG whitebox-database host $DATABASE_HOST

    iniset $TEMPEST_CONFIG whitebox-hardware cpu_topology "$WHITEBOX_CPU_TOPOLOGY"

    iniset $TEMPEST_CONFIG compute-feature-enabled virtio_rng "$COMPUTE_FEATURE_VIRTIO_RNG"
    iniset $TEMPEST_CONFIG compute-feature-enabled rbd_download "$COMPUTE_FEATURE_RBD_DOWNLOAD"
}

if [[ "$1" == "stack" ]]; then
    if is_service_enabled tempest; then
        if [[ "$2" == "test-config" ]]; then
            configure
        fi
    fi
fi
