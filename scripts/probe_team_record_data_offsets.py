from __future__ import annotations
import struct
from nba2k_editor.memory.game_memory import GameMemory
from nba2k_editor.models.data_model import EditorDataModel
from nba2k_editor.models.team_record_routing import _best_team_record_run, team_record_row_group


def f32(mem, addr):
    return struct.unpack('<f', mem.read_bytes(addr, 4))[0]


def main():
    mem=GameMemory('NBA2K26.exe')
    if not mem.open_process(): print('ATTACH failed'); return 2
    try:
        model=EditorDataModel(memory=mem,target_executable='NBA2K26.exe')
        model.refresh_domain_items('Teams',limit=1)
        item=model.selected_item('Teams')
        run=_best_team_record_run(model,item)
        print('item', item, 'run', run)
        if not run: return 1
        start,count,row_stride=run
        base=model.domain_base('NBA Records')
        # Points first row and FG Made first row according to current mapping
        for section, stat in [('Single Game (Regular)','Points'),('Single Game (Regular)','FG Made'),('Season','Points'),('Career','Points')]:
            row_start,row_count=team_record_row_group(section,stat)
            addr=base+(start//8+row_start)*row_stride
            row=model._record_summary_values_for_address('NBA Records',addr,1)
            print('\n', section, stat, 'row_start', row_start, 'addr', hex(addr), row)
            for off in range(48, 80, 4):
                try:
                    print(f'  +0x{off:02x}', f32(mem, addr+off))
                except Exception as exc:
                    print(f'  +0x{off:02x}', type(exc).__name__, exc)
        return 0
    finally: mem.close()
if __name__=='__main__': raise SystemExit(main())
