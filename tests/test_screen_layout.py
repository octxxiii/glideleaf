from types import SimpleNamespace
import sys

import pytest

from winuc.config import Config
from winuc.edge import EdgeStateMachine, PushResult
from winuc.gui.layout_diagram import clamp_center, draw_layout, layout_from_point


def test_layout_segment_limits_crossing_and_maps_entry_and_return():
    machine = EdgeStateMachine('right', 80, 80, (1000, 800),
                               layout_center_pct=75, layout_span_pct=50)
    machine.set_edge_geometry(1919, 0, 1000)
    assert not machine.hits_edge(1919, 499)
    assert machine.hits_edge(1919, 500)
    assert machine.hits_edge(1919, 1000)
    machine.begin_push(1919, 750, 0)
    assert machine.on_push_delta(80, 0, 10) == PushResult.CROSS
    assert abs(machine._vy - 0.5 * 799) < 1
    assert machine.force_local() == (1919, 750)


def test_top_layout_limits_horizontal_crossing_and_returns_within_segment():
    machine = EdgeStateMachine('top', 80, 80, (1000, 800),
                               layout_center_pct=30, layout_span_pct=40)
    machine.set_edge_geometry(0, 0, 1000)
    assert not machine.hits_edge(99, 0)
    assert machine.hits_edge(100, 0)
    assert machine.hits_edge(500, 0)
    assert not machine.hits_edge(501, 0)
    machine.begin_push(300, 0, 0)
    assert machine.on_push_delta(0, -80, 10) == PushResult.CROSS
    assert abs(machine._vx - .5 * 999) < 1
    assert machine.force_local() == (300, 0)


@pytest.mark.parametrize('edge,point', [
    ('left', (100, 140)), ('right', (420, 140)),
    ('top', (260, 0)), ('bottom', (260, 300)),
])
def test_layout_drag_snaps_to_each_side(edge, point):
    assert layout_from_point(*point, (160, 70, 360, 210), 50)[0] == edge
    assert clamp_center(0, 75) == 38
    assert clamp_center(100, 75) == 62


def test_layout_configuration_roundtrip_and_old_default(tmp_path):
    path = tmp_path / 'config.json'
    config = Config(edge='top', layout_center_pct=65, layout_span_pct=60)
    config.save(path)
    saved = Config.load(path)
    assert (saved.edge, saved.layout_center_pct, saved.layout_span_pct) == ('top', 65, 60)
    path.write_text('{"edge":"left"}', encoding='utf-8')
    old = Config.load(path)
    assert (old.layout_center_pct, old.layout_span_pct) == (50, 100)
    with pytest.raises(ValueError):
        Config(layout_center_pct=90, layout_span_pct=50).validate()


@pytest.mark.parametrize('height,compact', [(140, False), (116, True)])
@pytest.mark.parametrize('edge', ['left', 'right', 'top', 'bottom'])
def test_diagram_boxes_fit_small_windows(height, compact, edge):
    class Canvas:
        rectangles = []
        def delete(self, *_args):
            self.rectangles = []
        def winfo_width(self):
            return 700
        def winfo_height(self):
            return height
        def create_rectangle(self, x1, y1, x2, y2, **_kwargs):
            self.rectangles.append((x1, y1, x2, y2))
        def create_text(self, *_args, **_kwargs):
            pass
        def create_line(self, *_args, **_kwargs):
            pass
    canvas = Canvas()
    draw_layout(canvas, edge, 70, 50, compact=compact)
    assert len(canvas.rectangles) == 2
    assert all(0 <= x1 < x2 <= 700 and 0 <= y1 < y2 <= height
               for x1, y1, x2, y2 in canvas.rectangles)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows Tk desktop')
def test_layout_picker_drag_saves_selected_side_and_segment(desktop_root):
    from winuc.gui.settings import SettingsWindow
    saved = []
    window = SettingsWindow(desktop_root, Config(), saved.append)
    try:
        desktop_root.update()
        window.vars['layout_span_pct'].set(50)
        window._render_layout()
        x1, y1, x2, y2 = window._layout_pc
        point = SimpleNamespace(x=round(x1 - 35), y=round(y1 + (y2 - y1) * .7))
        window._start_layout_drag(point)
        window._apply_values()
        assert saved
        assert (saved[0].edge, saved[0].layout_center_pct, saved[0].layout_span_pct) == ('left', 70, 50)
    finally:
        if window.win.winfo_exists():
            window.win.destroy()
