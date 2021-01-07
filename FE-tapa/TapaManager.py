#! /usr/bin/python3.6
import sys
sys.path.append('../FE')
from collections import defaultdict
from DataflowGraphTapa import DataflowGraphTapa
from ProgramJsonManager import ProgramJsonManager
from DeviceManager import DeviceManager
from Floorplan import Floorplanner
from Slot import Slot
from AXIConnectionParser import AXIConnectionParser

import logging
import json
import re
import os

class TapaManager:
  def __init__(self, config_file_path):
    self.__setupLogging(logging.DEBUG)
    assert os.path.isfile(config_file_path)
    
    self.config = json.loads(open(config_file_path, 'r').read())
    assert self.config['CompiledBy'] == 'TAPA'

    self.project_path = self.config['ProjectPath']
    self.top_name = self.config['TopName']
    self.device_manager = DeviceManager(self.config['Board'])
    self.board = self.device_manager.getBoard()
    self.top_rtl_path = f'{self.project_path}/hdl/{self.top_name}_{self.top_name}.v'

    self.axi_parser = AXIConnectionParser(self.top_rtl_path)
    self.program_json_manager = ProgramJsonManager(self.project_path, self.top_name)
    self.graph = DataflowGraphTapa(self.program_json_manager, self.axi_parser)

    user_constraint_s2v = self.parseUserConstraints()
    
    self.fp = Floorplanner(self.graph, user_constraint_s2v, total_usage=self.program_json_manager.getVertexTotalArea(), board=self.board)
    self.fp.coarseGrainedFloorplan()
    self.generateTAPAConstraints()

  def generateTAPAConstraints(self):
    s2v = self.fp.getSlotToVertices()
    output = {slot.getNameConsiderVitisIP() : [v.name for v in v_group] for slot, v_group in s2v.items()}
    f = open('tapa_constraint.json', 'w')
    f.write(json.dumps(output, indent=2))

  def parseUserConstraints(self):
    port_bining = self.config['ExternalPortBinding']

    user_constraint_s2v = defaultdict(list)

    # for m_axi modules
    for region, axi_group in port_bining.items():
      slot = Slot(self.board, region)
      for axi_name in axi_group:
        io_module_name = self.axi_parser.getIOModuleNameOfAXI(axi_name)
        user_constraint_s2v[slot].append(self.graph.getVertex(io_module_name))

    # for s_axi_control
    slot = Slot(self.board, 'COARSE_X1Y0')
    s_axi_ctrl_name = self.axi_parser.getSAXIName()
    user_constraint_s2v[slot].append(self.graph.getVertex(s_axi_ctrl_name))

    # for optional module constraints
    module_fp = self.config['OptionalFloorplan']
    for region, module_group in module_fp.items():
      slot = Slot(self.board, region)
      for mod_name in module_group:
        user_constraint_s2v[slot].append(self.graph.getVertex(mod_name))

    return user_constraint_s2v

  def __setupLogging(self, level):
    logging.basicConfig(filename='auto-parallel.log', filemode='w', level=level, format="[%(levelname)s: %(funcName)25s() ] %(message)s")

if __name__ == "__main__":
  m = TapaManager('SampleUserConfig.json')