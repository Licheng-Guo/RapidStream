import argparse
import logging
import json
import math
import os
import sys
from typing import Set, Dict, Tuple

from rapidstream.BE.GenAnchorConstraints import createAnchorPlacementExtractScript, __getBufferRegionSize
from rapidstream.BE.Device import U250
from rapidstream.BE.Utilities import loggingSetup

loggingSetup()


def getHeader(slot1_name, slot2_name):
  header = ['\n\n`timescale 1 ns / 1 ps',
            f'module {slot1_name}_AND_{slot2_name} (']
  return header

def getIODecl(slot1_io : dict, slot2_io : dict, wrapper_io : dict):
  slot_io_merge = {**slot1_io, **slot2_io}
  io_decl = [f'  {" ".join(slot_io_merge[io])} {io},' for io in wrapper_io]
  io_decl[-1] = io_decl[-1].replace(',', ');')
  
  return io_decl

def getConnection(inner_connection):
  """
  get the RTL to connect the slots
  data links will be pipelined
  wires of passing edge will be directly connected
  @param connection: the RTL section
  @param pipeline_reg: all the pipeline registers instantiated
  """
  connection = []
  pipeline_regs = []

  pipeline_level = 1  # keep this for historical reason

  if args.invert_non_laguna_anchor_clock:
    clock_edge = 'negedge'
  else:
    clock_edge = 'posedge'

  for io, dir_width in inner_connection.items():
    width = dir_width[1] if len(dir_width) == 2 else ''
    connection.append(f'  wire {width} {io}_in;')
    connection.append(f'  wire {width} {io}_out;')

    # assign the input wire equals the output wire
    if pipeline_level == 0:
      assert False
      connection.append(f'  assign {io}_in = {io}_out;')
    else:
      # add the pipeline registers
      for i in range(pipeline_level):
        connection.append(f'  (* dont_touch = "yes" *) reg {width} {io}_q{i};')
        
        # format: input/output width name
        # to be used for placement extraction
        pipeline_regs.append(dir_width + [f'{io}_q{i}'])
    
      # connect the head and tail
      connection.append(f'  always @ ({clock_edge} ap_clk) begin')
      connection.append(f'    {io}_q0 <= {io}_out;')
      for i in range(1, pipeline_level):
        connection.append(f'    {io}_q{i} <= {io}_q{i-1};')
      connection.append(f'  end')
      connection.append(f'  assign {io}_in = {io}_q{pipeline_level-1};')

  return connection, pipeline_regs

def getInstance(slot_name : str, slot_io : dict, wrapper_io : dict, inner_connection : dict):
  instance = []
  instance.append(f'  (* black_box *) {slot_name} {slot_name}_U0 (')
  for io, dir_width in slot_io.items():
    if io in wrapper_io:
      instance.append(f'    .{io}({io}),')
    elif io in inner_connection:
      if 'input' in dir_width:
        instance.append(f'    .{io}({io}_in),')
      elif 'output' in dir_width:
        instance.append(f'    .{io}({io}_out),')
      else:
        assert False
    else:
      assert False
  instance[-1] = instance[-1].replace(',', ');\n')

  return instance

def getEmptyWrapper(slot_name, slot_io):
  """ in order for black_box modules to be recognized by vivado """
  empty_wrapper = []
  empty_wrapper.append(f'\n\nmodule {slot_name} (')
  empty_wrapper += [' '.join(dir_width) + ' ' + io + ',' for io, dir_width in slot_io.items()]
  empty_wrapper[-1] = empty_wrapper[-1].replace(',', '')
  empty_wrapper.append(f');')
  empty_wrapper.append(f'endmodule')
  return empty_wrapper

def getTopIOAndInnerConnectionOfPair(slot1_name, slot2_name) -> Tuple[Set, Dict]:
  slot1_io = hub['SlotIO'][slot1_name]
  slot2_io = hub['SlotIO'][slot2_name]

  # io name -> dir + width (in string)
  convert = lambda slot_io : {io[-1] : io[0:-1] for io in slot_io }
  slot1_io = convert(slot1_io)
  slot2_io = convert(slot2_io)

  # common io of the two slots
  inner_connection = {k : v for k, v in slot1_io.items() if k in slot2_io}
  
  # external io of the wrapper
  wrapper_io = slot1_io.keys() - slot2_io.keys() | \
           slot2_io.keys() - slot1_io.keys()

  # deal with ap_clk
  wrapper_io.add('ap_clk')
  inner_connection.pop('ap_clk')

  return wrapper_io, inner_connection

def getPairWrapper(slot1_name, slot2_name):
  """ 
  group together two neighbor slots 
  Wires of passing edges should not be pipelined
  Also create the script to extract the placement of pipeline registers
  """
  slot1_io = hub['SlotIO'][slot1_name]
  slot2_io = hub['SlotIO'][slot2_name]

  # io name -> dir + width (in string)
  convert = lambda slot_io : {io[-1] : io[0:-1] for io in slot_io }
  slot1_io = convert(slot1_io)
  slot2_io = convert(slot2_io)

  wrapper_io, inner_connection = getTopIOAndInnerConnectionOfPair(slot1_name, slot2_name)

  header = getHeader(slot1_name, slot2_name)
  io_decl = getIODecl(slot1_io, slot2_io, wrapper_io)

  # pipelined connection between the two slots
  connection, pipeline_regs = getConnection(inner_connection)

  slot1_inst = getInstance(slot1_name, slot1_io, wrapper_io, inner_connection)
  slot2_inst = getInstance(slot2_name, slot2_io, wrapper_io, inner_connection)
  ending = ['endmodule\n']

  slot1_def = getEmptyWrapper(slot1_name, slot1_io)
  slot2_def = getEmptyWrapper(slot2_name, slot2_io)

  pair_wrapper = header + io_decl + connection + slot1_inst + slot2_inst + ending + slot1_def + slot2_def

  return pair_wrapper, pipeline_regs


def CreateWrapperForSlotPair(slot1_name, slot2_name):
  pair_name = f'{slot1_name}_AND_{slot2_name}'
  pair_wrapper, pipeline_regs = getPairWrapper(slot1_name, slot2_name)
  
  open(f'{baseline_dir}/{pair_name}/{pair_name}.v', 'w').write('\n'.join(pair_wrapper))

  # in the meantime create the placement extraction script
  createAnchorPlacementExtractScript(pair_name, pipeline_regs, f'{baseline_dir}/{pair_name}')


def createVivadoScriptForSlotPair(
    slot1_name,
    slot2_name,
    output_dir):
  pair_name = f'{slot1_name}_AND_{slot2_name}'

  fpga_part_name = hub["FPGA_PART_NAME"]

  script = []

  script.append(f'set_part {fpga_part_name}')

  # read in the original RTLs by HLS
  script.append(f'read_verilog {baseline_dir}/{pair_name}/{pair_name}.v')  

  # clock xdc
  script.append(f'read_xdc ./clock.xdc')

  # synth
  script.append(f'synth_design -top "{pair_name}" -part {fpga_part_name} -mode out_of_context')
  script.append(f'write_checkpoint synth.dcp')

  # make Vivado place the anchors on lagunas
  # will be automatically invalidated for non-SLR-crossing pairs
  script.append(f'set_property USER_SLL_REG 1 [get_cells -regexp {{ .*q0_reg.* }} ]')

  # read in the dcp of slots
  script.append(f'read_checkpoint -cell {slot1_name}_U0 {placement_dir}/{slot1_name}/{slot1_name}_placed_no_anchor.dcp')
  script.append(f'read_checkpoint -cell {slot2_name}_U0 {placement_dir}/{slot2_name}/{slot2_name}_placed_no_anchor.dcp')
  
  script.append(f'delete_pblock [get_pblock *]')
  script.append(f'lock_design -level placement')

  # constrain the pipeline registers. get the pblocks based on slot names
  script.append(f'create_pblock anchor_region')
  script.append(f'set_property IS_SOFT 0 [get_pblocks anchor_region]')

  # corner case: there may be no anchors between two slots
  script.append( 'catch {add_cells_to_pblock [get_pblocks anchor_region] [get_cells -regexp {.*q0_reg.*} ] }')

  col_width, row_width = __getBufferRegionSize(None, None) # TODO: should automatically choose a suitable buffer region size
  
  # the region will be used by Vivado to place the anchors
  # if we only include lagunas, it will fail placement DRC check
  # thus we include the lagunas and the SLICE nearby
  anchor_region_def = U250.getBufferRegionBetweenSlotPair(slot1_name, slot2_name, col_width, row_width, include_laguna=True)

  # note that we need to include lagunas into the pblocks
  # otherwise the placer will deem no SLL could be used
  # since there are only 1 pipeline register, the registers will not be placed onto laguna sites (which require a pair)
  script.append(f'resize_pblock [get_pblocks anchor_region] -add {{{anchor_region_def}}}')

  # report the anchor usage of the buffer region
  script.append(f'report_utilization -pblocks [get_pblocks anchor_region]')

  # place and anchors
  script.append(f'place_design')

  # extract anchor placement
  script.append(f'source {pair_name}_print_anchor_placement.tcl')

  script.append(f'write_checkpoint {pair_name}_placed.dcp')

  open(f'{output_dir}/place.tcl', 'w').write('\n'.join(script))
  open(f'{output_dir}/clock.xdc', 'w').write(f'create_clock -name ap_clk -period {args.clock_period} [get_ports ap_clk]')


def getParallelScript():
  task = []
  for slot1_name, slot2_name in hub["AllSlotPairs"]:
    pair_name = f'{slot1_name}_AND_{slot2_name}'

    cd = f'cd {baseline_dir}/{pair_name}'

    if args.which_iteration == 0:
      get_guard = lambda slot_name: f'{placement_dir}/{slot_name}/{slot_name}_placed.dcp.done.flag'
    else:
      get_guard = lambda slot_name: f'{placement_dir}/{slot_name}/{slot_name}_post_placed_opt.dcp.done.flag'

    guard1 = f'until [ -f {get_guard(slot1_name)} ]; do sleep 10; done'
    guard2 = f'until [ -f {get_guard(slot2_name)} ]; do sleep 10; done'

    vivado = f'VIV_VER={args.vivado_version} vivado -mode batch -source place.tcl'

    transfer = []
    for server in server_list:
      transfer.append(f'rsync -azhv --delete -r {baseline_dir}/{pair_name}/ {user_name}@{server}:{baseline_dir}/{pair_name}/')
    transfer_str = " && ".join(transfer)

    task.append(f'{cd} && {guard1} && {guard2} && {vivado} && {transfer_str}')

  num_job_server = math.ceil(len(task) / len(server_list) ) 
  for i, server in enumerate(server_list):
    local_tasks = task[i * num_job_server: (i+1) * num_job_server]
    open(f'{baseline_dir}/parallel_baseline_vivado_anchor_placement_iter{args.which_iteration}_{server}.txt', 'w').write('\n'.join(local_tasks))

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument("--hub_path", type=str, required=True)
  parser.add_argument("--base_dir", type=str, required=True)
  parser.add_argument("--vivado_version", type=str, required=True)
  parser.add_argument("--which_iteration", type=int, required=True)
  parser.add_argument("--clock_period", type=float, required=True)
  parser.add_argument("--invert_non_laguna_anchor_clock", type=int, required=True)
  parser.add_argument("--server_list_in_str", type=str, required=True, help="e.g., \"u5 u15 u17 u18\"")
  parser.add_argument("--user_name", type=str, required=True)
  args = parser.parse_args()

  hub_path = args.hub_path
  base_dir = args.base_dir
  user_name = args.user_name
  server_list = args.server_list_in_str.split()

  hub = json.loads(open(hub_path, 'r').read())

  synth_dir = f'{base_dir}/slot_synth'

  if args.which_iteration == 0:
    placement_dir = f'{base_dir}/init_slot_placement'
  else:
    placement_dir = f'{base_dir}/baseline_vivado_anchor_placement_opt_iter{args.which_iteration-1}'

  baseline_dir = f'{base_dir}/baseline_vivado_anchor_placement_iter{args.which_iteration}'
  os.mkdir(baseline_dir)

  for slot1_name, slot2_name in hub["AllSlotPairs"]:
    pair_name = f'{slot1_name}_AND_{slot2_name}'
    os.mkdir(f'{baseline_dir}/{pair_name}')

    CreateWrapperForSlotPair(slot1_name, slot2_name)
    createVivadoScriptForSlotPair(slot1_name, slot2_name, f'{baseline_dir}/{pair_name}')
    
  getParallelScript()