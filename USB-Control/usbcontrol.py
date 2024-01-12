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

    parser.add_argument('-s', '--host',
                        required=True,
                        action='store',
                        help='Remote host to connect to')

    parser.add_argument('-o', '--port',
                        required=False,
                        action='store',
                        help="port to use, default 443", default=443)

    parser.add_argument('-u', '--user',
                        required=True,
                        action='store',
                        help='User name to use when connecting to host')

    parser.add_argument('-p', '--password',
                        required=False,
                        action='store',
                        help='Password to use when connecting to host')

    parser.add_argument('-v', '--vm_name',
                        required=True,
                        action='store',
                        help='Name of the virtual machine to connect to')

    parser.add_argument('-f', '--filter',
                        required=False,
                        action='store',
                        help='Filter for USB device descriptions (e.g., "Ralink")',
                        default='')

    parser.add_argument('--usb_version',
                        required=False,
                        choices=['2.0', '3.2'],
                        default='3.2',
                        help='USB controller version to add (2.0 or 3.2)')

    args = parser.parse_args()
    password = None
    if args.password is None:
        password = getpass.getpass(
            prompt='Enter password for host %s and user %s: ' %
                   (args.host, args.user))
    args = parser.parse_args()
    if password:
        args.password = password
    return args


args = get_args()

context = ssl._create_unverified_context()

service_instance = SmartConnect(host=args.host, user=args.user, pwd=args.password, port=args.port, sslContext=context)

atexit.register(Disconnect, service_instance)

content = service_instance.RetrieveContent()

def add_usb_3_2_controller(vm):
    # Check if the required USB controller already exists
    for device in vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualUSBXHCIController):  # Assuming this is the class for USB 3.2
            print("USB 3.2 Controller already exists on VM:", vm.name)
            return

    # Create a new USB 3.2 controller
    usb_controller = vim.vm.device.VirtualUSBXHCIController()  # Assuming this is the class for USB 3.2
    usb_controller.busNumber = 0
    usb_controller.key = -101  # Unique key, different from USB 2.0 controller
    usb_controller.deviceInfo = vim.Description()
    usb_controller.deviceInfo.label = 'USB 3.2 Controller'
    usb_controller.deviceInfo.summary = 'USB 3.2 Controller'

    # Create the Virtual Device Spec
    spec = vim.vm.ConfigSpec()
    dev_changes = []
    dev_spec = vim.vm.device.VirtualDeviceSpec()
    dev_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
    dev_spec.device = usb_controller
    dev_changes.append(dev_spec)

    spec.deviceChange = dev_changes
    task = vm.ReconfigVM_Task(spec=spec)

    # Wait for the task to complete
    while task.info.state == vim.TaskInfo.State.running:
        time.sleep(1)

    if task.info.state == vim.TaskInfo.State.error:
        print("Error adding USB 3.2 Controller to VM:", vm.name)
        if task.info.error:
            print(task.info.error)
        return False
    return True



def add_usb_controller(vm):
    # Check if a USB controller already exists
    for device in vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualUSBController):
            print("USB Controller already exists on VM:", vm.name)
            return

    # Create a new USB 2.0 controller
    usb_controller = vim.vm.device.VirtualUSBController()
    usb_controller.busNumber = 0
    usb_controller.key = -100
    usb_controller.deviceInfo = vim.Description()
    usb_controller.deviceInfo.label = 'USB Controller'
    usb_controller.deviceInfo.summary = 'USB 2.0 Controller'

    # Create the Virtual Device Spec
    spec = vim.vm.ConfigSpec()
    dev_changes = []
    dev_spec = vim.vm.device.VirtualDeviceSpec()
    dev_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
    dev_spec.device = usb_controller
    dev_changes.append(dev_spec)

    spec.deviceChange = dev_changes
    task = vm.ReconfigVM_Task(spec=spec)

    # Wait for the task to complete
    while task.info.state == vim.TaskInfo.State.running:
        time.sleep(1)

    if task.info.state == vim.TaskInfo.State.error:
        print("Error adding USB Controller to VM:", vm.name)
        if task.info.error:
            print(task.info.error)
        return False
    return True


def find_vm_by_name(content, vm_name):
    vm_view = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
    for vm in vm_view.view:
        if vm.name == vm_name:
            return vm
    return None

selected_vm = find_vm_by_name(content, args.vm_name)
if selected_vm is None:
    raise SystemExit(f"VM '{args.vm_name}' not found")

def addOrRemoveKey(vm, device, remove=False):
    usb_changes = []
    vm_spec = vim.vm.ConfigSpec()
    usb_spec = vim.vm.device.VirtualDeviceSpec()

    if remove:
        usb_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.remove
    else:
        usb_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add

    if isinstance(device, str):
        usb_spec.device = vim.vm.device.VirtualUSB()
        usb_spec.device.backing = vim.vm.device.VirtualUSB.USBBackingInfo()
        usb_spec.device.backing.deviceName = device
    else:
        usb_spec.device = device
    usb_changes.append(usb_spec)

    vm_spec.deviceChange = usb_changes
    task = vm.ReconfigVM_Task(spec=vm_spec)

    while task.info.state == vim.TaskInfo.State.running:
        time.sleep(1)

    if task.info.state == vim.TaskInfo.State.error:
        msg = "Error adding {0} to {1}" if not remove else "Error removing {0} from {1}"
        device_name = device if isinstance(device, str) else device.backing.deviceName
        print(msg.format(device_name, vm.name))
        print("--------------------------")
        print("VCenter error message")
        print(task.info.error)
        print("--------------------------")
        return False
    return True

datacenter = content.rootFolder.childEntity[0]
viewType = [vim.HostSystem]
containerView = content.viewManager.CreateContainerView(datacenter, viewType, True)
hosts_in_datacenter = containerView.view

container = content.viewManager.CreateContainerView(datacenter, [vim.ComputeResource], True)
cluster_resource_container = container.view[0]

for host in hosts_in_datacenter:
    usb_devices_connected_to_host = []
    usb_devices_connected_to_vm = []

    for resource_container in cluster_resource_container.host:
        if host.name != resource_container.name:
            continue
        host_info = cluster_resource_container.environmentBrowser.QueryConfigTarget(host)
        if len(host_info.usb) < 1:
            print('No USB device is connected to host ' + host.name)
        else:
            print('----------------------------------------------------')
            print('List connected USB devices to host (filtered with -f) ' + host.name)
            print('---------------------')

            for usb in host_info.usb:
                usb_physical_path = usb.physicalPath
                if args.filter in usb.description:
                    usb_devices_connected_to_host.append(usb_physical_path)
                    print(usb.description, usb_physical_path)

            print('---------------------')

        selected_vm = find_vm_by_name(content, args.vm_name)
        if selected_vm is None:
            raise SystemExit(f"VM '{args.vm_name}' not found")

        if args.usb_version == '2.0':
            add_usb_controller(selected_vm)
        elif args.usb_version == '3.2':
            add_usb_3_2_controller(selected_vm)
        

        for device in selected_vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualUSB):
                usb_devices_connected_to_vm.append(device.backing.deviceName)

    for usb_device in usb_devices_connected_to_host:
        if usb_device not in usb_devices_connected_to_vm:
            addOrRemoveKey(selected_vm, usb_device)
            print(f'USB device {usb_device} was connected to VM: "{selected_vm.name}"')
