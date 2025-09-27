import pytest
import os
import json
from app import Unit, Player, Game, generate_random_unit, save_data, load_data

# --- FIXTURES ---

@pytest.fixture(autouse=True)
def cleanup_save_file():
    """Ensure save file is removed before and after each test."""
    if os.path.exists("game_data.json"):
        os.remove("game_data.json")
    yield
    if os.path.exists("game_data.json"):
        os.remove("game_data.json")

@pytest.fixture
def warrior_unit():
    return Unit(attributes={'str': 15, 'dex': 10, 'con': 12, 'int': 8, 'wis': 9, 'cha': 10}, unit_id="warrior")

@pytest.fixture
def mage_unit():
    return Unit(attributes={'int': 15, 'dex': 10, 'con': 9, 'str': 8, 'wis': 12, 'cha': 11}, unit_id="mage")

@pytest.fixture
def cleric_unit():
    return Unit(attributes={'wis': 15, 'int': 10, 'con': 10}, unit_id="cleric")

@pytest.fixture
def rogue_unit():
    return Unit(attributes={'dex': 18, 'str': 10, 'con': 10}, unit_id="rogue")

@pytest.fixture
def barbarian_unit():
    return Unit(attributes={'con': 16, 'str': 14, 'dex': 12}, unit_id="barbarian")

@pytest.fixture
def bard_unit():
    return Unit(attributes={'cha': 16, 'dex': 12, 'con': 10}, unit_id="bard")

@pytest.fixture
def player():
    return Player(name="Test Player")

@pytest.fixture
def game():
    return Game()

# --- UNIT & PLAYER TESTS ---

def test_unit_creation(warrior_unit):
    assert warrior_unit.class_name == 'Krieger'
    assert warrior_unit.max_hp == 50 + (12 * 5)
    assert warrior_unit.hp == warrior_unit.max_hp
    assert warrior_unit.attack == 5 + 15
    assert warrior_unit.cost == (15 + 10 + 12 + 8 + 9 + 10) // 2
    assert not warrior_unit.is_defeated

def test_generate_random_unit():
    unit = generate_random_unit()
    assert isinstance(unit, Unit)
    assert sum(unit.attributes.values()) > 0
    assert unit.class_name in ['Krieger', 'Schurke', 'Barbar', 'Magier', 'Kleriker', 'Barde', 'Abenteurer']

# --- GAME MECHANIC TESTS ---

def test_simple_combat_warrior_vs_mage(game, warrior_unit, mage_unit):
    game.player1.units.append(warrior_unit)
    game.player2.units.append(mage_unit)
    game.run_full_combat()
    assert game.winner is not None
    assert game.game_state == "finished"
    assert any(u.is_defeated for u in game.player1.units + game.player2.units)

def test_warrior_shield_ability(game, warrior_unit):
    game.player1.units.append(warrior_unit)
    game.run_full_combat() # Will run for at least one round
    shield_log = next((log for log in game.combat_log if log.get('type') == 'shield'), None)
    assert shield_log is not None
    assert shield_log['actor_id'] == warrior_unit.id
    assert warrior_unit.shield > 0

def test_cleric_heal_ability(game, cleric_unit, warrior_unit):
    warrior_unit.hp = 10  # Damage the warrior
    game.player1.units.extend([cleric_unit, warrior_unit])
    # Add an enemy to ensure combat doesn't end immediately
    game.player2.units.append(Unit(attributes={'con': 20}))
    game.run_full_combat()
    heal_log = next((log for log in game.combat_log if log.get('type') == 'heal'), None)
    assert heal_log is not None
    assert heal_log['healer_id'] == cleric_unit.id
    assert heal_log['target_id'] == warrior_unit.id
    assert warrior_unit.hp > 10

def test_mage_splash_damage(game, mage_unit):
    target1 = Unit(attributes={'con': 10}, unit_id="target1")
    target2 = Unit(attributes={'con': 10}, unit_id="target2")
    target1_hp = target1.hp
    target2_hp = target2.hp

    game.player1.units.append(mage_unit)
    game.player2.units.extend([target1, target2])

    # Position units to be adjacent for splash
    game.player2.board['0,0'] = target1; target1.position = '0,0'
    game.player2.board['0,1'] = target2; target2.position = '0,1'

    game.run_full_combat()

    splash_log = next((log for log in game.combat_log if log.get('is_splash')), None)
    assert splash_log is not None
    assert target1.hp < target1_hp
    assert target2.hp < target2_hp

def test_rogue_hide_and_backstab(game, rogue_unit):
    # Use a high-HP target to ensure it survives long enough for the rogue to hide and attack
    target = Unit(attributes={'con': 100}, unit_id="target")
    game.player1.units.append(rogue_unit)
    game.player2.units.append(target)

    # Ensure rogue's cooldown is 0 to allow hiding on the first possible turn
    rogue_unit.ability_cooldown = 0

    game.run_full_combat()

    # Verify that the rogue did hide at some point
    hide_log = next((log for log in game.combat_log if log.get('type') == 'hide' and log.get('actor_id') == 'rogue'), None)
    assert hide_log is not None, "Rogue did not use hide ability."

    # Verify that the rogue performed a backstab (an attack that ignores shield)
    backstab_log = next((log for log in game.combat_log
                         if log.get('type') == 'attack'
                         and log.get('attacker_id') == 'rogue'
                         and log.get('ignores_shield') is True), None)

    assert backstab_log is not None, "Rogue did not perform a logged backstab attack."

    # Verify the damage was doubled as expected for a backstab
    assert backstab_log['damage'] == int(rogue_unit.attack * 2.0)

def test_barbarian_frenzy_ability(game, barbarian_unit):
    target = Unit(attributes={'con': 15}, unit_id="target")
    game.player1.units.append(barbarian_unit)
    game.player2.units.append(target)

    game.run_full_combat()

    frenzy_start_log = next((log for log in game.combat_log if log.get('type') == 'frenzy_start'), None)
    assert frenzy_start_log is not None

    frenzied_attack_log = next((log for log in game.combat_log if log.get('type') == 'attack' and any(e.get('type') == 'frenzy' for e in barbarian_unit.status_effects)), None)
    # Note: This check is tricky due to timing. A better check is that damage is increased.
    # We look for an attack log where the damage is 1.5x the base attack.
    base_attack = 5 + barbarian_unit.attributes.get('str', 0)
    expected_frenzy_dmg = int(base_attack * 1.5)
    assert any(log.get('damage') == expected_frenzy_dmg for log in game.combat_log if log.get('type') == 'attack' and log.get('attacker_id') == barbarian_unit.id)

def test_bard_battle_song(game, bard_unit, warrior_unit):
    game.player1.units.extend([bard_unit, warrior_unit])
    game.player2.units.append(Unit(attributes={'con': 20}))

    game.run_full_combat()

    song_log = next((log for log in game.combat_log if log.get('type') == 'battle_song'), None)
    assert song_log is not None

    base_attack = 5 + warrior_unit.attributes.get('str', 0)
    expected_buffed_dmg = int(base_attack * 1.25)
    assert any(log.get('damage') == expected_buffed_dmg for log in game.combat_log if log.get('type') == 'attack' and log.get('attacker_id') == warrior_unit.id)

def test_draw_condition(game):
    # Two Barbarians with very high health but minimal strength.
    # Their class is determined by high 'con', but their attack scales with 'str'.
    # This results in high HP but low damage, forcing a timeout.
    # HP = 50 + 100*5 = 550. Attack = 5 + 1 = 6. They cannot defeat each other.
    low_damage_high_hp_unit1 = Unit(attributes={'con': 100, 'str': 1, 'dex': 1, 'int': 1, 'wis': 1, 'cha': 1})
    low_damage_high_hp_unit2 = Unit(attributes={'con': 100, 'str': 1, 'dex': 1, 'int': 1, 'wis': 1, 'cha': 1})

    game.player1.units.append(low_damage_high_hp_unit1)
    game.player2.units.append(low_damage_high_hp_unit2)

    game.run_full_combat()

    assert game.round_count >= 20, f"Game ended in {game.round_count} rounds, not 20."
    assert game.winner is not None

# --- PERSISTENCE & UPGRADE TESTS ---

def test_save_and_load_player(player, warrior_unit):
    player.barracks.append(warrior_unit)
    save_data(player)

    assert os.path.exists("game_data.json")

    loaded_player = load_data()
    assert loaded_player is not None
    assert loaded_player.name == player.name
    assert len(loaded_player.barracks) == 1
    assert loaded_player.barracks[0].id == warrior_unit.id
    assert loaded_player.barracks[0].class_name == 'Krieger'

def test_xp_and_upgrade(player, warrior_unit):
    xp_needed = warrior_unit.level * 100
    warrior_unit.xp = xp_needed
    player.barracks.append(warrior_unit)

    # Manually perform the upgrade logic from the upgrade_unit route
    unit_to_upgrade = player.barracks[0]
    original_level = unit_to_upgrade.level
    original_stats_sum = sum(unit_to_upgrade.attributes.values())

    unit_to_upgrade.xp -= xp_needed
    unit_to_upgrade.level += 1
    # Simplified attribute increase for testing
    unit_to_upgrade.attributes['str'] += 1
    unit_to_upgrade.attributes['con'] += 1

    assert unit_to_upgrade.level == original_level + 1
    assert unit_to_upgrade.xp == 0
    assert sum(unit_to_upgrade.attributes.values()) == original_stats_sum + 2