import sys
import json
import re
import os

from autoparallel.BE.SlotRouting import addSomeAnchors, removePlaceholderAnchors
from autoparallel.BE.Utilities import getSlotsInSLRIndex, loggingSetup

loggingSetup()

SLR_NUM = 4


def getVivadoScriptForSLR(slr_index):

  script = []

  # this will be generated by RW after the stitching
  script.append(f'source -notrace {slr_stitch_dir}/slr_{slr_index}/slr_{slr_index}_load.tcl')
  
  script.append('report_route_status')
  
  # to verify the tap of row buffers
  script.append(f'set fp [open "clock_route.txt" "w" ]') # to check the row buffer tap
  script.append(f'puts $fp [get_property ROUTE [get_nets ap_clk]]')
  script.append(f'close $fp')
  script.append(f'report_timing_summary')

  script.append(f'delete_pblocks *')

  # relax the clock 
  script.append(f'create_clock -name ap_clk -period 3 [get_pins test_bufg/O]')
  script.append(f'set_clock_uncertainty -hold 0.02 [get_clocks ap_clk]')

  script.append(f'write_checkpoint {slr_stitch_dir}/slr_{slr_index}/pre_route_checkpoint/slr_{slr_index}_before_routed.dcp')
  script.append(f'write_edif {slr_stitch_dir}/slr_{slr_index}/pre_route_checkpoint/slr_{slr_index}_before_routed.edf')

  # add back the placeholder FFs
  script += addSomeAnchors(hub, base_dir, getSlotsInSLRIndex(hub, slr_index))

  script.append(f'route_design -preserve')

  # remove the placeholder anchors
  script += removePlaceholderAnchors()

  script.append(f'write_checkpoint {slr_stitch_dir}/slr_{slr_index}/vivado_routed_checkpoint/slr_{slr_index}_routed.dcp')
  script.append(f'write_edif {slr_stitch_dir}/slr_{slr_index}/vivado_routed_checkpoint/slr_{slr_index}_routed.edf')

  return script


def getParallelTasks():
  all_tasks = []
  for slr_index in range(SLR_NUM):
    slots = getSlotsInSLRIndex(hub, slr_index)

    cd = f'cd {slr_stitch_dir}/slr_{slr_index}'
    rw_source = f'source {RW_SETUP_PATH}'
    get_dcp_regexp = lambda slot_name: f'(.*{slot_name}.*non_laguna_anchor_nets_unrouted.dcp)'
    all_dcp_regexps = '|'.join([get_dcp_regexp(slot_name) for slot_name in slots])
    rw = f'java com.xilinx.rapidwright.examples.MergeDCP {slot_routing_dir} slr_{slr_index}.dcp "{all_dcp_regexps}"'

    vivado = f'VIV_VER={VIV_VER} vivado -mode batch -source {slr_stitch_dir}/slr_{slr_index}/route_slr_{slr_index}.tcl'

    stitch = f'{cd} && {rw_source} && {rw} && {vivado}'

    all_tasks.append(stitch)

  open(f'{slr_stitch_dir}/parallel-route-slr.txt', 'w').write('\n'.join(all_tasks))


if __name__ == '__main__':
  assert len(sys.argv) == 5, 'input (1) the path to the front end result file and (2) the target directory'
  hub_path = sys.argv[1]
  base_dir = sys.argv[2]
  VIV_VER=sys.argv[3]
  RW_SETUP_PATH = sys.argv[4]

  hub = json.loads(open(hub_path, 'r').read())

  slr_stitch_dir = f'{base_dir}/SLR_level_stitch'
  os.mkdir(slr_stitch_dir)

  slot_routing_dir = f'{base_dir}/slot_routing'

  anchor_placement_dir = f'{base_dir}/ILP_anchor_placement_iter0'
  anchor_source_placement_script = 'place_laguna_anchor_source_cells.tcl'

  for slr_index in range(SLR_NUM):
    os.mkdir(f'{slr_stitch_dir}/slr_{slr_index}')
    os.mkdir(f'{slr_stitch_dir}/slr_{slr_index}/vivado_routed_checkpoint')
    os.mkdir(f'{slr_stitch_dir}/slr_{slr_index}/rwroute_routed_checkpoint')
    os.mkdir(f'{slr_stitch_dir}/slr_{slr_index}/pre_route_checkpoint')

  for slr_index in range(SLR_NUM):
    script = getVivadoScriptForSLR(slr_index)

    open(f'{slr_stitch_dir}/slr_{slr_index}/route_slr_{slr_index}.tcl', 'w').write('\n'.join(script))

  getParallelTasks()