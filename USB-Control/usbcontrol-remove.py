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
    parser.add_argument('-f', '--filter', required=False, action='store', help='Filter for USB device descriptions (e.g., "Ralink")')

    args = parser.parse_args()
    password = None
    if args.password is None:
        password = getpass.getpass(prompt='Enter password for host %s and user %s: ' % (args.host, args.user))
    args = parser.parse_args()
    if password:
        args.password = password
    return args


def find_vm_by_name(content, vm_name):
    vm_view = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
    for vm in vm_view.view:
        if vm.name == vm_name:
            return vm
    return None


def remove_all_usb_devices(vm):
    usb_changes = []
    
    for device in vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualUSB):
            usb_spec = vim.vm.device.VirtualDeviceSpec()
            usb_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.remove
            usb_spec.device = device
            usb_changes.append(usb_spec)

    if not usb_changes:
        print(f"No USB devices found in VM: {vm.name}")
        return True  # No devices to remove

    vm_spec = vim.vm.ConfigSpec()
    vm_spec.deviceChange = usb_changes
    task = vm.ReconfigVM_Task(spec=vm_spec)

    while task.info.state == vim.TaskInfo.State.running:
        time.sleep(1)

    if task.info.state == vim.TaskInfo.State.error:
        print(f"Error removing USB devices from VM {vm.name}")
        print("--------------------------")
        print("VCenter error message")
        print(task.info.error)
        print("--------------------------")
        return False
    return True


def remove_usb_devices_by_filter(vm, filter_text):
    usb_changes = []
    devices_removed = False  # Track if any devices were removed
    
    for device in vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualUSB):
            device_summary = device.deviceInfo.summary.lower()  # Convert to lowercase for case-insensitive comparison
            filter_text = filter_text.lower()  # Convert filter text to lowercase

            print(f"Filter Text: {filter_text}")
            print(f"Device Description: {device_summary}")

            if filter_text in device_summary:
                usb_spec = vim.vm.device.VirtualDeviceSpec()
                usb_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.remove
                usb_spec.device = device
                usb_changes.append(usb_spec)
                devices_removed = True  # Set to True if at least one device is removed

    if not usb_changes:
        print(f"No USB devices found with filter '{filter_text}' in VM: {vm.name}")
        return True  # No devices to remove

    vm_spec = vim.vm.ConfigSpec()
    vm_spec.deviceChange = usb_changes
    task = vm.ReconfigVM_Task(spec=vm_spec)

    while task.info.state == vim.TaskInfo.State.running:
        time.sleep(1)

    if task.info.state == vim.TaskInfo.State.error:
        print(f"Error removing USB devices with filter '{filter_text}' from VM {vm.name}")
        print("--------------------------")
        print("VCenter error message")
        print(task.info.error)
        print("--------------------------")
        return False
    
    if devices_removed:
        print(f'Removed USB devices with filter "{filter_text}" from VM: "{vm.name}"')
    else:
        print(f"No USB devices found with filter '{filter_text}' in VM: {vm.name}")

    return True


args = get_args()

context = ssl._create_unverified_context()

service_instance = SmartConnect(host=args.host, user=args.user, pwd=args.password, port=args.port, sslContext=context)

atexit.register(Disconnect, service_instance)

content = service_instance.RetrieveContent()

selected_vm = find_vm_by_name(content, args.vm_name)
if selected_vm is None:
    raise SystemExit(f"VM '{args.vm_name}' not found")

if args.filter:
    success = remove_usb_devices_by_filter(selected_vm, args.filter)
else:
    success = remove_all_usb_devices(selected_vm)

if success:
    print(f'Operation completed for VM: "{selected_vm.name}"')
