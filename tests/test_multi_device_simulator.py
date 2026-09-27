from simulator.solix_multi_sim.solix_sim.profiles import PLUG_PROFILE, STORAGE_PROFILES
from simulator.solix_multi_sim.solix_sim.world.household_world import HouseholdWorld


def test_shared_household_world_preserves_energy_balance():
    world = HouseholdWorld()
    snapshot = world.tick(60)
    assert snapshot.balance_residual_w == 0
    assert snapshot.home_load_w == snapshot.base_load_w + snapshot.controllable_load_w
    assert snapshot.grid_w == snapshot.home_load_w - snapshot.pv_w - snapshot.battery_w


def test_plug_action_changes_meter_truth_and_cumulative_energy():
    world = HouseholdWorld()
    before = world.tick(0)
    energy_before = world.plug_energy_kwh
    world.plug_on = False
    after = world.tick(60)
    assert before.home_load_w - after.home_load_w == PLUG_PROFILE.rated_power_w
    assert before.grid_w - after.grid_w == PLUG_PROFILE.rated_power_w
    assert world.plug_energy_kwh == energy_before


def test_storage_action_changes_grid_and_soc_with_profile_limits():
    world = HouseholdWorld()
    profile = STORAGE_PROFILES[0]
    storage = world.storages[profile.key]
    before = world.tick(0)
    storage.requested_battery_w = 1000
    after = world.tick(60)
    assert after.grid_w == before.grid_w - 1000
    assert storage.soc < profile.initial_soc


def test_storage_reserve_blocks_discharge():
    world = HouseholdWorld()
    profile = STORAGE_PROFILES[0]
    storage = world.storages[profile.key]
    storage.soc = 30
    storage.backup_reserve = 30
    storage.requested_battery_w = 1000
    world.tick(1)
    assert storage.battery_w == 0
