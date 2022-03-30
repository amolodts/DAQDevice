#!/usr/bin/env python3

import tango
from tango import DevState, Attr, READ
from tango.server import Device, command, device_property

from uldaq import (get_daq_device_inventory, DaqDevice, InterfaceType,
                   DigitalDirection, DigitalPortIoType)



class DAQDevice(Device):
    
    #properties
    Port_types_A=device_property(
        dtype=bool,
        default_value=True
        )
    Port_types_B=device_property(
        dtype=bool,
        default_value=True
        )
    Port_types_C=device_property(
        dtype=bool,
        default_value=True
        )
    Port_types_Counter=device_property(
        dtype=bool,
        default_value=True
        )
    Descriptor_index=device_property(
        dtype=int,
        default_value=0
        )


    def init_device(self):
        Device.init_device(self)
        self.set_state(DevState.INIT)
        interface_type = InterfaceType.ANY
 
        # Get descriptors for all of the available DAQ devices.
        self.devices = get_daq_device_inventory(interface_type)
        self.number_of_devices = len(self.devices)
        if self.number_of_devices == 0:
            self.set_state(DevState.ALARM)
            self.set_status('Error: No DAQ devices found')
        else:
            # Create the DAQ device from the descriptor at the specified index.
            self.daq_device = DaqDevice(self.devices[self.Descriptor_index])
    
            # Get the DioDevice object and verify that it is valid.
            self.dio_device = self.daq_device.get_dio_device()
            
            if self.dio_device is None:
                self.set_state(DevState.ALARM)
                self.set_status('Error: The DAQ device does not support digital input')
            else:
                
                # Establish a connection to the DAQ device.
                self.descriptor = self.daq_device.get_descriptor()
                self.daq_device.connect(connection_code=0)
                self.set_state(DevState.INIT)
                self.set_status('Establish a connection to the DAQ device {:s}'.format(self.descriptor.dev_string))
        
      
    def initialize_dynamic_attributes(self):
        # create automaticly attributes and read methodes of all ports for enabled port_type
        print('Initialisierung mit: ', self.Port_types_A)
        port_types = [self.Port_types_A, self.Port_types_B, self.Port_types_C, self.Port_types_Counter]
        port_type_index=['A','B','C','Counter']
        DYN_ATTRS = []
        k=0

        for i in port_types:
            if i==True and self.Port_types_Counter!=True:
                for j in range(0,8):
                    port = dict(name='{typ}{nr}'.format(typ=port_type_index[k], nr=str(j)), 
                                dtype=tango.DevBoolean, access=READ)
                    DYN_ATTRS.append(port)
            elif i==True and self.Port_types_Counter==True:
                port = dict(name='CTR', dtype=tango.DevInt, access=READ)
                DYN_ATTRS.append(port)
                
            k+=1
            
        if DYN_ATTRS:
            for d in DYN_ATTRS:
                self.set_status('Ports have been selected.')
                self.make_attribute(d)
        else:
            self.set_status("No ports are selected. Select a port type, refresh the Attributes and restart the device's jive interfaces to see changes.")
            
    def make_attribute(self, attr_dict):
        props = ['name','dtype','access'] 
        attr_dict_ = attr_dict.copy()
        
        # remove key-value-paar and print out value of entry k
        name, dtype, access= [attr_dict_.pop(k) for k in props]
        new_attr = Attr(name, dtype, access)
        prop = tango.UserDefaultAttrProp()  

        # build attribute for all enabled ports
        for k, v in attr_dict.items():
            try:
                property_setter = getattr(prop, 'set_' + k)
                property_setter(v)
            except AttributeError:
                print("error setting attribute property:", name, k, v,file=self.log_error)
            new_attr.set_default_properties(prop)
            self.add_attribute(
                new_attr,
                r_meth=self.read_general,
                )
        else:
            print(f'Skipping attribute {name}: Does not exist on this device',
                  file=self.log_warn)
            
  
    def read_general(self, attr):
        # read out data
        # data is passed as a byte for each port_type and every bit represents a port; 1.bit = 1.port of port_type ...
        key=7-int(list(attr.get_name())[1])
        port_type = list(attr.get_name())[0]
        # port_types_index: 0 = PortA, 1 = PortB, 2 = PortC)
        if port_type == 'A':
            port_types_index = 0
        elif port_type == 'B':
            port_types_index = 1
        elif port_type == 'C':
            port_types_index = 2
        else:
            port_types_index = 3 #this is the counter

        attr.set_value(self.data_get(key, port_types_index))

    def data_get(self, key, port_types_index):
        #function to communicate with port_type input
        
        # Get the port types for the device(AUXPORT, FIRSTPORTA, ...)
        self.dio_info = self.dio_device.get_info()
        self.port_types = self.dio_info.get_port_types()

        # [<DigitalPortType.FIRSTPORTA: 10>, <DigitalPortType.FIRSTPORTB: 11>,
        # <DigitalPortType.FIRSTPORTC: 12>, <DigitalPortType.FIRSTPORTCH: 13>]
        
        if port_types_index >= len(self.port_types):
            port_types_index = len(self.port_types) - 1

        self.port_to_read = self.port_types[port_types_index]
        
        # Configure the port for input.
        self.port_info = self.dio_info.get_port_info(self.port_to_read)

        if (self.port_info.port_io_type == DigitalPortIoType.IO or
                self.port_info.port_io_type == DigitalPortIoType.BITIO):
            self.dio_device.d_config_port(self.port_to_read, DigitalDirection.INPUT)
        
        while True:
            self.set_state(DevState.RUNNING)
            self.set_status('Reading data')
            self.data = self.dio_device.d_in(self.port_to_read)
            if port_types_index==3:
                return self.data
            else:
                data_bit_list=list(format(self.data,'08b'))
                if int(data_bit_list[key]) == 0:
                    return False
                else:
                    return True
                
        
    @command
    def refreshAtt(self):
        self.initialize_dynamic_attributes()
                    
        
    def delete_device(self):
        if self.daq_device:
            if self.daq_device.is_connected():
                self.daq_device.disconnect()
            self.daq_device.release()
            


        
if __name__ == '__main__':
    DAQDevice.run_server()