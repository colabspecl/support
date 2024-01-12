import argparse
import atexit
import getpass
import time

from pyVim import connect
from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect
import ssl


def get_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('-s', '--host', required=True, action='store', help='Remote host to connect to')
    parser.add_argument('-o', '--port', required=False, action='store', help="Port to use, default 443", default=443)
    parser.add_argument('-u', '--user', required=True, action='store', help='User name to use when connecting to host')
    parser.add_argument('-p', '--password', required=False, action='store', help='Password to use when connecting to host')
    parser.add_argument('-v', '--vm_name', required=True, action='store', help='Name of the virtual machine to connect to')
    parser.add_argument('-f', '--filter', required=False, action='store', help='Filter for USB device descriptions (e.g., "Ralink")', default='')

    args = parser.parse_args()
    password = None
    if args.password is None:
        password = getpass.getpass(prompt='Enter password for host %s and user %s: ' % (args.host, args.user))
    args = parser.parse_args()
    if password:
        args.password = password
    return args


args = get_args()

context = ssl._create_unverified_context()

service_instance = SmartConnect(host=args.host, user=args.user, pwd=args.password, port=args.port, sslContext=context)

atexit.register(Disconnect, service_instance)

content = service_instance.RetrieveContent()


def find_vm_by_name(content, vm_name):
    vm_view = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
    for vm in vm_view.view:
        if vm.name == vm_name:
            return vm
    return None


selected_vm = find_vm_by_name(content, args.vm_name)
if selected_vm is None:
    raise SystemExit(f"VM '{args.vm_name}' not found")


def remove_usb_device(vm, usb_device):
    usb_changes = []
    usb_spec = vim.vm.device.VirtualDeviceSpec()
    usb_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.remove
    usb_spec.device = usb_device

    usb_changes.append(usb_spec)

    vm_spec = vim.vm.ConfigSpec()
    vm_spec.deviceChange = usb_changes
    task = vm.ReconfigVM_Task(spec=vm_spec)

    while task.info.state == vim.TaskInfo.State.running:
        time.sleep(1)

    if task.info.state == vim.TaskInfo.State.error:
        print(f"Error removing USB device {usb_device.backing.deviceName} from VM {vm.name}")
        print("--------------------------")
        print("VCenter error message")
        print(task.info.error)
        print("--------------------------")
        return False
    return True


datacenter = content.rootFolder.childEntity[0]
container = content.viewManager.CreateContainerView(datacenter, [vim.ComputeResource], True)
cluster_resource_container = container.view[0]

usb_devices_connected_to_vm = [device for device in selected_vm.config.hardware.device if isinstance(device, vim.vm.device.VirtualUSB)]

for usb_device in usb_devices_connected_to_vm:
    device_name = usb_device.backing.deviceName
    print(f"Checking USB device {device_name}...")  # Debug: Print the name of each USB device

    if args.filter in device_name:
        success = remove_usb_device(selected_vm, usb_device)
        if success:
            print(f'USB device {device_name} was removed from VM: "{selected_vm.name}"')
    else:
        print(f"Skipping USB device {device_name} as it does not match the filter '{args.filter}'")  # Debug: Print a message when skipping a device
