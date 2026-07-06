from winuc.edge import EdgeStateMachine, PushResult, State


def make_machine(edge="right", push=80, ret=80, speed=1.0):
    machine = EdgeStateMachine(
        edge=edge,
        push_threshold_px=push,
        return_threshold_px=ret,
        remote_size=(1000, 800),
        speed=speed,
    )
    # PC 画面: 0..1919 x 0..1079 の right エッジ相当
    if edge in ("right", "left"):
        machine.set_edge_geometry(1919 if edge == "right" else 0, 0, 1079)
    else:
        machine.set_edge_geometry(0 if edge == "top" else 1079, 0, 1919)
    return machine


def test_hits_edge():
    machine = make_machine("right")
    assert machine.hits_edge(1919, 500)
    assert not machine.hits_edge(1918, 500)
    assert not machine.hits_edge(1919, 2000)

    machine = make_machine("left")
    assert machine.hits_edge(0, 500)
    assert not machine.hits_edge(1, 500)


def test_push_through_crosses():
    machine = make_machine("right", push=80)
    machine.begin_push(1919, 540, now_ms=0)
    assert machine.state == State.PUSHING
    assert machine.on_push_delta(30, 0, 10) == PushResult.STAY
    assert machine.on_push_delta(30, 5, 20) == PushResult.STAY
    assert machine.on_push_delta(30, 0, 30) == PushResult.CROSS
    assert machine.state == State.REMOTE


def test_push_cancel_on_retreat():
    machine = make_machine("right")
    machine.begin_push(1919, 540, now_ms=0)
    assert machine.on_push_delta(10, 0, 10) == PushResult.STAY
    assert machine.on_push_delta(-40, 0, 20) == PushResult.CANCEL
    assert machine.state == State.LOCAL


def test_push_idle_resets_accumulator():
    machine = make_machine("right", push=80)
    machine.begin_push(1919, 540, now_ms=0)
    assert machine.on_push_delta(70, 0, 10) == PushResult.STAY
    # 500ms 途切れる → 蓄積リセット、次の 70px では越えない
    assert machine.on_push_delta(70, 0, 600) == PushResult.STAY
    assert machine.on_push_delta(20, 0, 610) == PushResult.CROSS


def test_remote_entry_position_maps_laterally():
    machine = make_machine("right")
    machine.begin_push(1919, 540, now_ms=0)  # 縦方向のちょうど中央
    while machine.state == State.PUSHING:
        machine.on_push_delta(50, 0, 10)
    assert machine.state == State.REMOTE
    assert machine._vx == 0.0
    assert abs(machine._vy - 0.5 * 799) < 1.0


def test_remote_motion_and_return():
    machine = make_machine("right", ret=80)
    machine.begin_push(1919, 540, now_ms=0)
    machine.on_push_delta(100, 0, 10)
    assert machine.state == State.REMOTE

    # iPad 内を右へ移動
    motion = machine.on_remote_delta(100, 10)
    assert (motion.dx, motion.dy) == (100, 10)
    assert not motion.exited

    # ゆっくり左端へ戻り、端で押し込むと戻る
    machine.on_remote_delta(-60, 0)   # vx=40, まだ内側
    result = machine.on_remote_delta(-70, 0)   # 30px 突き抜け → acc=70
    assert not result.exited
    result = machine.on_remote_delta(-20, 0)   # acc=90 >= 80
    assert result.exited
    assert machine.state == State.LOCAL
    x, y = result.exit_point
    assert x == 1919
    assert 0 <= y <= 1079


def test_remote_fast_slam_returns_immediately():
    machine = make_machine("right", ret=80)
    machine.begin_push(1919, 540, now_ms=0)
    machine.on_push_delta(100, 0, 10)
    machine.on_remote_delta(500, 0)  # iPad の内側へ
    result = machine.on_remote_delta(-2000, 0)  # 勢いよく PC 方向へ
    assert result.exited


def test_remote_return_resets_when_moving_away():
    machine = make_machine("right", ret=100)
    machine.begin_push(1919, 540, now_ms=0)
    machine.on_push_delta(100, 0, 10)
    machine.on_remote_delta(-30, 0)   # 30px 突き抜け → acc=30
    machine.on_remote_delta(10, 0)    # 内側へ → acc リセット, vx=10
    result = machine.on_remote_delta(-80, 0)  # acc = 70+10 = 80 < 100
    assert not result.exited
    assert machine.state == State.REMOTE


def test_speed_scaling_with_carry():
    machine = make_machine("right", speed=0.5)
    machine.begin_push(1919, 540, now_ms=0)
    machine.on_push_delta(100, 0, 10)
    total = 0
    for _ in range(10):
        motion = machine.on_remote_delta(1, 0)
        total += motion.dx
    assert total == 5  # 0.5 倍が端数繰り越しで正確に反映される


def test_force_local():
    machine = make_machine("right")
    machine.begin_push(1919, 540, now_ms=0)
    machine.on_push_delta(100, 0, 10)
    assert machine.state == State.REMOTE
    x, y = machine.force_local()
    assert machine.state == State.LOCAL
    assert x == 1919


def test_left_edge():
    machine = make_machine("left")
    machine.begin_push(0, 540, now_ms=0)
    assert machine.on_push_delta(-100, 0, 10) == PushResult.CROSS
    assert machine._vx == 999.0  # iPad の右端から入る
    machine.on_remote_delta(-500, 0)  # iPad の内側 (左) へ
    machine.on_remote_delta(400, 0)   # 右端の手前まで戻る (vx=899, depth=100)
    result = machine.on_remote_delta(200, 0)  # 100px 突き抜け → acc=200 >= 80
    assert result.exited
    assert result.exit_point[0] == 0
