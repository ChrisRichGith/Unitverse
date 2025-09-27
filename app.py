import uuid
import json
import os
from flask import Flask, render_template, redirect, url_for
import random

# --- DATA CLASSES ---

class Unit:
    def __init__(self, attributes, level=1, xp=0, unit_id=None):
        self.id = unit_id if unit_id else str(uuid.uuid4())
        self.level = level
        self.xp = xp
        self.attributes = attributes # e.g. {'str': 10, 'dex': 12, ...}

        # Determine class name
        # Find the attribute with the highest value
        primary_stat = max(self.attributes, key=self.attributes.get)
        class_map = {
            'str': 'Krieger', 'dex': 'Schurke', 'con': 'Barbar',
            'int': 'Magier', 'wis': 'Kleriker', 'cha': 'Barde'
        }
        self.class_name = class_map.get(primary_stat, 'Abenteurer')

        # Derive combat stats from attributes
        self.max_hp = 50 + (self.attributes.get('con', 0) * 5)
        self.hp = self.max_hp
        self.initiative = self.attributes.get('dex', 0)

        if self.class_name in ['Krieger', 'Barbar']:
            self.attack = 5 + self.attributes.get('str', 0)
        elif self.class_name in ['Schurke']:
            self.attack = 5 + self.attributes.get('dex', 0)
        elif self.class_name in ['Magier', 'Kleriker', 'Barde']:
            self.attack = 5 + self.attributes.get('int', 0)
        else:
            self.attack = 5

        # Calculate cost based on sum of attributes (halved to make it more affordable)
        self.cost = sum(self.attributes.values()) // 2

        self.is_defeated = False
        self.position = None
        self.shield = 0
        self.status_effects = [] # e.g. [{'type': 'frenzy', 'duration': 2}]
        self.frenzy_used = False
        self.is_hidden = False
        self.ability_cooldown = 0

    def to_dict(self):
        return {
            "id": self.id,
            "level": self.level,
            "xp": self.xp,
            "attributes": self.attributes,
        }

    @classmethod
    def from_dict(cls, data):
        # Handle old save data that doesn't have the new attribute structure
        if "attributes" not in data or not data["attributes"]:
            return None

        return Unit(
            attributes=data.get("attributes"),
            level=data.get("level", 1),
            xp=data.get("xp", 0),
            unit_id=data.get("id"),
        )

class Player:
    def __init__(self, name, is_ai=False):
        self.name = name
        self.is_ai = is_ai
        self.gold = 100
        self.units = []
        self.barracks = []
        self.board = {f"{r},{c}": None for r in range(2) for c in range(3)}

    def to_dict(self):
        return { "name": self.name, "barracks": [u.to_dict() for u in self.barracks] }

class Game:
    def __init__(self):
        self.player1 = Player(name="Spieler 1")
        self.player2 = Player(name="PC", is_ai=True)
        self.game_state = "title_screen"
        self.shop_units = []
        self.round_count = 0
        self.combat_log = []
        self.winner = None
        self.survivors = []

    def _perform_standard_attack(self, attacker):
        """A basic attack action for units on cooldown or without special abilities."""
        opponent_player = self.player2 if attacker in self.player1.units else self.player1
        target = next((u for u in opponent_player.units if not u.is_defeated and not u.is_hidden), None)
        if target:
            attack_sound = f"Attack_0{random.randint(1, 4)}.mp3"
            self._apply_damage(attacker, target, attacker.attack, sound=attack_sound)
        else:
            self.combat_log.append({'type': 'idle', 'actor_id': attacker.id, 'actor_name': attacker.class_name, 'reason': 'No target available'})

    def run_full_combat(self):
        """Simulates the entire combat from start to finish."""
        # Reset ability cooldowns at the start of combat
        for unit in self.player1.units + self.player2.units:
            unit.ability_cooldown = 0

        turn_order = sorted(self.player1.units + self.player2.units, key=lambda u: u.initiative, reverse=True)

        for i in range(20): # Max 20 rounds
            self.round_count = i + 1
            self.combat_log.append({'type': 'round', 'number': self.round_count})

            # --- STATUS EFFECT DURATION & COOLDOWN HANDLING ---
            for unit in turn_order:
                if unit.is_defeated: continue
                if unit.ability_cooldown > 0:
                    unit.ability_cooldown -= 1
                for effect in list(unit.status_effects):
                    effect['duration'] -= 1
                    if effect['duration'] <= 0:
                        unit.status_effects.remove(effect)
                        self.combat_log.append({'type': 'effect_end', 'unit_id': unit.id, 'unit_name': unit.class_name, 'effect': effect['type']})

            for attacker in turn_order:
                if attacker.is_defeated:
                    continue

                # Log which player's turn it is
                active_player_id = "player1" if attacker in self.player1.units else "player2"
                self.combat_log.append({'type': 'active_player_turn', 'player_id': active_player_id})

                # --- ACTION LOGIC ---
                if attacker.class_name == 'Kleriker':
                    if attacker.ability_cooldown == 0:
                        allied_player = self.player1 if attacker in self.player1.units else self.player2
                        heal_candidates = [u for u in allied_player.units if not u.is_defeated and u.hp < u.max_hp]
                        if heal_candidates:
                            heal_candidates.sort(key=lambda u: u.hp / u.max_hp)
                            target = heal_candidates[0]
                            heal_amount = 5 + attacker.attributes.get('wis', 0)
                            original_hp = target.hp
                            target.hp = min(target.max_hp, target.hp + heal_amount)
                            self.combat_log.append({
                                'type': 'heal', 'healer_id': attacker.id, 'healer_name': attacker.class_name,
                                'target_id': target.id, 'target_name': target.class_name,
                                'heal_amount': target.hp - original_hp, 'target_hp_after': target.hp,
                                'target_max_hp': target.max_hp, 'sound': 'Kleriker.mp3'
                            })
                            attacker.ability_cooldown = 2
                        else:
                            self._perform_standard_attack(attacker)
                    else:
                        self._perform_standard_attack(attacker)

                elif attacker.class_name == 'Krieger':
                    if attacker.ability_cooldown == 0:
                        shield_amount = 10 + attacker.attributes.get('str', 0)
                        attacker.shield += shield_amount
                        self.combat_log.append({
                            'type': 'shield', 'actor_id': attacker.id, 'actor_name': attacker.class_name,
                            'shield_amount': shield_amount, 'shield_total': attacker.shield,
                            'sound': 'Krieger.mp3'
                        })
                        attacker.ability_cooldown = 3
                    else:
                        self._perform_standard_attack(attacker)

                elif attacker.class_name == 'Magier':
                    if attacker.ability_cooldown == 0:
                        opponent_player = self.player2 if attacker in self.player1.units else self.player1
                        main_target = next((u for u in opponent_player.units if not u.is_defeated and not u.is_hidden), None)
                        if main_target:
                            splash_targets = self._get_adjacent_units(main_target, opponent_player)
                            all_target_ids = [main_target.id] + [t.id for t in splash_targets if t != main_target and not t.is_defeated and not t.is_hidden]
                            self.combat_log.append({'type': 'splash_preview', 'attacker_id': attacker.id, 'target_ids': all_target_ids})
                            self._apply_damage(attacker, main_target, attacker.attack, sound='Magier.mp3')
                            for splash_target in splash_targets:
                                if splash_target != main_target and not splash_target.is_defeated and not splash_target.is_hidden:
                                    self._apply_damage(attacker, splash_target, int(attacker.attack * 0.5), is_splash=True)
                            attacker.ability_cooldown = 2
                        else:
                            self._perform_standard_attack(attacker)
                    else:
                        self._perform_standard_attack(attacker)

                elif attacker.class_name == 'Barde':
                    if attacker.ability_cooldown == 0:
                        allied_player = self.player1 if attacker in self.player1.units else self.player2
                        self.combat_log.append({'type': 'battle_song', 'actor_id': attacker.id, 'actor_name': attacker.class_name, 'sound': 'Barde.mp3'})
                        for ally in allied_player.units:
                            if not ally.is_defeated and ally.id != attacker.id and not any(e['type'] == 'battle_song' for e in ally.status_effects):
                                ally.status_effects.append({'type': 'battle_song', 'duration': 3})
                        attacker.ability_cooldown = 3
                    else:
                        self._perform_standard_attack(attacker)

                elif attacker.class_name == 'Schurke':
                    if attacker.is_hidden:
                        opponent_player = self.player2 if attacker in self.player1.units else self.player1
                        target = next((u for u in opponent_player.units if not u.is_defeated and not u.is_hidden), None)
                        if target:
                            self._apply_damage(attacker, target, int(attacker.attack * 2.0), ignores_shield=True, sound='Schurke.mp3')
                        attacker.is_hidden = False
                        self.combat_log.append({'type': 'unhide', 'actor_id': attacker.id, 'actor_name': attacker.class_name})
                    elif attacker.ability_cooldown == 0:
                        attacker.is_hidden = True
                        self.combat_log.append({'type': 'hide', 'actor_id': attacker.id, 'actor_name': attacker.class_name, 'sound': 'Schurke.mp3'})
                        attacker.ability_cooldown = 2
                    else:
                        self._perform_standard_attack(attacker)

                else: # Barbar and Abenteurer
                    if attacker.class_name == 'Barbar' and attacker.ability_cooldown == 0:
                        attacker.status_effects.append({'type': 'frenzy', 'duration': 3})
                        self.combat_log.append({'type': 'frenzy_start', 'actor_id': attacker.id, 'actor_name': attacker.class_name, 'sound': 'Barbar.mp3'})
                        attacker.ability_cooldown = 4

                    self._perform_standard_attack(attacker)

                if self.check_game_over():
                    break

            if self.check_game_over():
                break

        self.determine_winner()
        self.game_state = "finished"

    def _apply_damage(self, attacker, target, damage, is_splash=False, ignores_shield=False, sound=None):
        if any(e['type'] == 'frenzy' for e in attacker.status_effects):
            damage = int(damage * 1.5)
        if any(e['type'] == 'battle_song' for e in attacker.status_effects):
            damage = int(damage * 1.25)

        if not ignores_shield:
            damage_to_shield = min(target.shield, damage)
            target.shield -= damage_to_shield
            remaining_damage = damage - damage_to_shield
        else:
            remaining_damage = damage

        target.hp = max(0, target.hp - remaining_damage)

        log_entry = {
            'type': 'attack', 'attacker_id': attacker.id, 'attacker_name': attacker.class_name,
            'target_id': target.id, 'target_name': target.class_name, 'damage': damage,
            'target_hp_after': target.hp, 'target_shield_after': target.shield, 'is_splash': is_splash,
            'ignores_shield': ignores_shield, 'target_max_hp': target.max_hp
        }
        if sound:
            log_entry['sound'] = sound
        if target.hp == 0:
            target.is_defeated = True
            log_entry['defeated'] = True
            # Overwrite attack sound with dying sound if defeated
            log_entry['sound'] = f"Dying_0{random.randint(1, 3)}.mp3"
        self.combat_log.append(log_entry)

    def _get_adjacent_units(self, target_unit, opponent_player):
        if not target_unit.position:
            return []

        r, c = map(int, target_unit.position.split(','))
        adjacent_positions = [
            (r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)
        ]

        adjacent_units = []
        for r_adj, c_adj in adjacent_positions:
            unit = opponent_player.board.get(f"{r_adj},{c_adj}")
            if unit:
                adjacent_units.append(unit)
        return adjacent_units

    def check_game_over(self):
        p1_alive = any(not u.is_defeated for u in self.player1.units)
        p2_alive = any(not u.is_defeated for u in self.player2.units)
        return not p1_alive or not p2_alive

    def _calculate_total_hp_percentage(self, player):
        if not player.units: return 0
        total_current_hp = sum(u.hp for u in player.units)
        total_max_hp = sum(u.max_hp for u in player.units)
        return (total_current_hp / total_max_hp) * 100 if total_max_hp > 0 else 0

    def determine_winner(self):
        p1_alive = any(not u.is_defeated for u in self.player1.units)
        p2_alive = any(not u.is_defeated for u in self.player2.units)

        if not p2_alive:
            self.winner = self.player1.name
        elif not p1_alive:
            self.winner = self.player2.name
        elif self.round_count >= 20:
            p1_hp_pct = self._calculate_total_hp_percentage(self.player1)
            p2_hp_pct = self._calculate_total_hp_percentage(self.player2)
            if p1_hp_pct > p2_hp_pct:
                self.winner = self.player1.name
            elif p2_hp_pct > p1_hp_pct:
                self.winner = self.player2.name
            else:
                self.winner = "Unentschieden"

        if self.winner == self.player1.name:
            # Calculate XP based on the defeated opponent's team value
            xp_pool = sum(u.cost for u in self.player2.units)

            # Find survivors
            surviving_units = [u for u in self.player1.units if not u.is_defeated]

            if surviving_units:
                # Distribute the XP pool among the survivors
                xp_per_survivor = xp_pool // len(surviving_units)
                for unit in surviving_units:
                    unit.xp += xp_per_survivor
                    self.survivors.append(unit)

# --- UNIT GENERATION ---
def generate_random_unit():
    """Generates a unit with D&D-style attributes."""
    attributes = {
        'str': random.randint(8, 15), 'dex': random.randint(8, 15),
        'con': random.randint(8, 15), 'int': random.randint(8, 15),
        'wis': random.randint(8, 15), 'cha': random.randint(8, 15),
    }
    return Unit(attributes=attributes)

# --- PERSISTENCE ---
SAVE_FILE = "game_data.json"

def save_data(player):
    with open(SAVE_FILE, "w") as f:
        json.dump(player.to_dict(), f, indent=4)

def load_data():
    if not os.path.exists(SAVE_FILE):
        return None
    with open(SAVE_FILE, "r") as f:
        try:
            data = json.load(f)
            player = Player(name=data.get("name", "Spieler 1"))
            loaded_units = [Unit.from_dict(u_data) for u_data in data.get("barracks", [])]
            player.barracks = [unit for unit in loaded_units if unit is not None]
            return player
        except (json.JSONDecodeError, KeyError):
            return None

# --- FLASK APP ---
app = Flask(__name__)
game = Game()

CLASS_ICONS = {
    'Krieger': '⚔️', 'Schurke': '🏹', 'Barbar': '🪓',
    'Magier': '🔮', 'Kleriker': '✨', 'Barde': '🎵',
    'Abenteurer': '🧑‍'
}

@app.route('/')
def index():
    global game
    # If a combat was just finished, reset the game object for a clean slate,
    # which will default to the title_screen state.
    if game.game_state == "finished":
        game = Game()

    save_exists = os.path.exists(SAVE_FILE)
    return render_template('index.html', game=game, save_exists=save_exists, class_icons=CLASS_ICONS)

@app.route('/start_game', methods=['POST'])
def start_game():
    global game
    game = Game()
    player_data = load_data()
    if player_data:
        game.player1 = player_data
    game.game_state = "preparation"
    game.shop_units = [generate_random_unit() for _ in range(4)]
    return render_template('index.html', game=game, save_exists=os.path.exists(SAVE_FILE), class_icons=CLASS_ICONS)


@app.route('/new_game', methods=['POST'])
def new_game():
    """Clears save data and starts a fresh game."""
    global game
    if os.path.exists(SAVE_FILE):
        os.remove(SAVE_FILE)

    # Set up the new game state directly
    game = Game()
    game.game_state = "preparation"
    game.shop_units = [generate_random_unit() for _ in range(4)]

    # Render the template directly
    return render_template('index.html', game=game, save_exists=False, class_icons=CLASS_ICONS)

@app.route('/buy_unit/<unit_id>', methods=['POST'])
def buy_unit(unit_id):
    if game.game_state != "preparation":
        return redirect(url_for('index'))
    unit_to_buy = next((u for u in game.shop_units if u.id == unit_id), None)
    player = game.player1
    if unit_to_buy and player.gold >= unit_to_buy.cost:
        slot = next((pos for pos, unit in player.board.items() if unit is None), None)
        if slot:
            player.gold -= unit_to_buy.cost
            player.units.append(unit_to_buy)
            player.board[slot] = unit_to_buy
            game.shop_units.remove(unit_to_buy)
            # Add a new unit to replace the bought one
            game.shop_units.append(generate_random_unit())
    return redirect(url_for('index'))

@app.route('/deploy_unit/<unit_id>', methods=['POST'])
def deploy_unit(unit_id):
    if game.game_state != "preparation":
        return redirect(url_for('index'))
    player = game.player1
    unit_to_deploy = next((u for u in player.barracks if u.id == unit_id), None)
    is_already_deployed = any(u.id == unit_id for u in player.units)
    if unit_to_deploy and not is_already_deployed:
        slot = next((pos for pos, unit in player.board.items() if unit is None), None)
        if slot:
            deployed_unit = Unit.from_dict(unit_to_deploy.to_dict())
            player.units.append(deployed_unit)
            player.board[slot] = deployed_unit
    return redirect(url_for('index'))

@app.route('/start_combat', methods=['POST'])
def start_combat():
    if game.game_state != "preparation":
        return redirect(url_for('index'))
    ai_player = game.player2
    if not ai_player.units:
        # AI now strategically buys units
        candidate_units = sorted([generate_random_unit() for _ in range(10)], key=lambda u: u.cost)

        for unit_to_buy in candidate_units:
            # Stop if board is full or AI can't afford the unit
            if len(ai_player.units) >= 6 or ai_player.gold < unit_to_buy.cost:
                break

            slot = next((pos for pos, unit in ai_player.board.items() if unit is None), None)
            if slot:
                ai_player.gold -= unit_to_buy.cost
                unit_to_buy.position = slot
                ai_player.units.append(unit_to_buy)
                ai_player.board[slot] = unit_to_buy
            else:
                # No more slots, break
                break
    game.run_full_combat()
    return render_template('combat_replay.html', game=game, combat_log_json=json.dumps([log for log in game.combat_log]), show_animation=True, class_icons=CLASS_ICONS)

@app.route('/load_game', methods=['POST'])
def load_game():
    global game
    loaded_player = load_data()
    if loaded_player:
        game = Game()
        game.player1 = loaded_player
    return redirect(url_for('index'))

@app.route('/move_to_barracks/<unit_id>', methods=['POST'])
def move_to_barracks(unit_id):
    if game.game_state != "finished":
        return redirect(url_for('index'))
    survivor = next((u for u in game.survivors if u.id == unit_id), None)
    if survivor and len(game.player1.barracks) < 3:
        if not any(u.id == survivor.id for u in game.player1.barracks):
            barracks_copy = Unit.from_dict(survivor.to_dict())
            barracks_copy.hp = barracks_copy.max_hp
            game.player1.barracks.append(barracks_copy)
            game.survivors.remove(survivor)
            save_data(game.player1)
    return render_template('combat_replay.html', game=game, combat_log_json=json.dumps([log for log in game.combat_log]), show_animation=False, class_icons=CLASS_ICONS)

@app.route('/barracks')
def barracks():
    player_data = load_data()
    if not player_data:
        player_data = game.player1
    return render_template('barracks.html', player=player_data, class_icons=CLASS_ICONS)

@app.route('/upgrade_unit/<unit_id>', methods=['POST'])
def upgrade_unit(unit_id):
    player = load_data()
    if player:
        unit_to_upgrade = next((u for u in player.barracks if u.id == unit_id), None)
        if unit_to_upgrade:
            xp_needed = unit_to_upgrade.level * 100
            if unit_to_upgrade.xp >= xp_needed:
                unit_to_upgrade.xp -= xp_needed
                unit_to_upgrade.level += 1
                stats_to_upgrade = list(unit_to_upgrade.attributes.keys())
                for stat in random.sample(stats_to_upgrade, 2):
                    unit_to_upgrade.attributes[stat] += 1
                upgraded_unit = Unit.from_dict(unit_to_upgrade.to_dict())
                for i, u in enumerate(player.barracks):
                    if u.id == upgraded_unit.id:
                        player.barracks[i] = upgraded_unit
                        break
                save_data(player)
    return redirect(url_for('barracks'))


@app.route('/save_barracks', methods=['POST'])
def save_barracks():
    """Saves the current barracks state."""
    player = load_data()
    if player:
        save_data(player)
    return redirect(url_for('barracks'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)