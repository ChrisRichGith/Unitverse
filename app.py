import uuid
import json
import os
from flask import Flask, render_template, redirect, url_for, request, flash, session
import random
# --- DATA CLASSES ---

class Unit:
    def __init__(self, attributes, level=1, xp=0, unit_id=None, nickname=None):
        self.id = unit_id if unit_id else str(uuid.uuid4())
        self.level = level
        self.xp = xp
        self.attributes = attributes
        self.nickname = nickname
        self.from_barracks = False
        self.recalculate_stats()
        self.is_defeated = False
        self.is_hidden = False
        self.position = None
        self.shield = 0
        self.status_effects = []
        self.ability_cooldown = 0

    def recalculate_stats(self):
        """Recalculates derived stats after an attribute change."""
        primary_stat = max(self.attributes, key=self.attributes.get)
        class_map = {
            'str': 'Krieger', 'dex': 'Schurke', 'con': 'Barbar',
            'int': 'Magier', 'wis': 'Kleriker', 'cha': 'Barde'
        }
        self.class_name = class_map.get(primary_stat, 'Abenteurer')
        self.max_hp = 50 + (self.attributes.get('con', 0) * 5)
        self.hp = self.max_hp
        self.initiative = self.attributes.get('dex', 0)
        if self.class_name in ['Krieger', 'Barbar']: self.attack = 5 + self.attributes.get('str', 0)
        elif self.class_name in ['Schurke']: self.attack = 5 + self.attributes.get('dex', 0)
        elif self.class_name in ['Magier', 'Kleriker', 'Barde']: self.attack = 5 + self.attributes.get('int', 0)
        else: self.attack = 5
        self.cost = sum(self.attributes.values()) // 2

    def add_xp(self, amount):
        """Adds XP to the unit."""
        if self.is_defeated: return
        self.xp += amount

    def level_up_if_possible(self):
        """Checks for and applies level-ups if the unit has enough XP."""
        leveled_up = False
        while self.xp >= self.level * 100:
            self.xp -= self.level * 100
            self.level += 1
            leveled_up = True
            stats_to_upgrade = list(self.attributes.keys())
            num_to_upgrade = min(len(stats_to_upgrade), 2)
            for stat in random.sample(stats_to_upgrade, num_to_upgrade):
                self.attributes[stat] += 1
        if leveled_up:
            self.recalculate_stats()
        return leveled_up

    def to_dict(self):
        return { "id": self.id, "level": self.level, "xp": self.xp, "attributes": self.attributes, "nickname": self.nickname }

    @classmethod
    def from_dict(cls, data):
        if "attributes" not in data or not data["attributes"]: return None
        unit = Unit(attributes=data.get("attributes"), level=data.get("level", 1), xp=data.get("xp", 0), unit_id=data.get("id"), nickname=data.get("nickname"))
        return unit

class Player:
    def __init__(self, name, is_ai=False):
        self.name = name
        self.is_ai = is_ai
        self.gold = 100
        self.units = []
        self.barracks = []
        self.board = {f"{r},{c}": None for r in range(2) for c in range(3)}

    def to_dict(self):
        return {
            "name": self.name,
            "is_ai": self.is_ai,
            "gold": self.gold,
            "units": [u.to_dict() for u in self.units],
            "barracks": [u.to_dict() for u in self.barracks],
            "board": {pos: (unit.to_dict() if unit else None) for pos, unit in self.board.items()}
        }

    @classmethod
    def from_dict(cls, data):
        if not data: return None
        player = Player(name=data.get("name"), is_ai=data.get("is_ai", False))
        player.gold = data.get("gold", 100)
        player.units = [Unit.from_dict(u_data) for u_data in data.get("units", []) if u_data]
        player.barracks = [Unit.from_dict(u_data) for u_data in data.get("barracks", []) if u_data]

        board_data = data.get("board", {})
        player.board = {}
        # Ensure all board positions are present
        for r in range(2):
            for c in range(3):
                pos = f"{r},{c}"
                u_data = board_data.get(pos)
                player.board[pos] = Unit.from_dict(u_data) if u_data else None
        return player

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
        opponent_player = self.player2 if attacker in self.player1.units else self.player1
        target = next((u for u in opponent_player.units if not u.is_defeated and not u.is_hidden), None)
        if target:
            attack_sound = f"Attack_0{random.randint(1, 4)}.mp3"
            self._apply_damage(attacker, target, attacker.attack, sound=attack_sound)
        else:
            action_owner = "player1" if attacker in self.player1.units else "player2"
            self.combat_log.append({'type': 'idle', 'actor_id': attacker.id, 'actor_name': attacker.class_name, 'reason': 'No target available', 'player_owner': action_owner})

    def run_full_combat(self):
        for unit in self.player1.units + self.player2.units: unit.ability_cooldown = 0
        turn_order = sorted(self.player1.units + self.player2.units, key=lambda u: u.initiative, reverse=True)
        for i in range(20):
            self.round_count = i + 1
            self.combat_log.append({'type': 'round', 'number': self.round_count})
            for unit in turn_order:
                if unit.is_defeated: continue
                if unit.ability_cooldown > 0: unit.ability_cooldown -= 1
                for effect in list(unit.status_effects):
                    effect['duration'] -= 1
                    if effect['duration'] <= 0:
                        unit.status_effects.remove(effect)
                        effect_owner = "player1" if unit in self.player1.units else "player2"
                        self.combat_log.append({'type': 'effect_end', 'unit_id': unit.id, 'unit_name': unit.class_name, 'effect': effect['type'], 'player_owner': effect_owner})
            for attacker in turn_order:
                if attacker.is_defeated: continue
                action_owner = "player1" if attacker in self.player1.units else "player2"
                self.combat_log.append({'type': 'active_player_turn', 'player_id': action_owner})
                if attacker.class_name == 'Kleriker' and attacker.ability_cooldown == 0:
                    allied_player = self.player1 if attacker in self.player1.units else self.player2
                    heal_candidates = [u for u in allied_player.units if not u.is_defeated and u.hp < u.max_hp]
                    if heal_candidates:
                        heal_candidates.sort(key=lambda u: u.hp / u.max_hp)
                        target = heal_candidates[0]
                        heal_amount = 5 + attacker.attributes.get('wis', 0)
                        original_hp = target.hp
                        target.hp = min(target.max_hp, target.hp + heal_amount)
                        self.combat_log.append({'type': 'heal', 'healer_id': attacker.id, 'healer_name': attacker.class_name, 'target_id': target.id, 'target_name': target.class_name, 'heal_amount': target.hp - original_hp, 'target_hp_after': target.hp, 'target_max_hp': target.max_hp, 'sound': 'Priest_Healing.mp3', 'player_owner': action_owner})
                        attacker.ability_cooldown = 2
                    else: self._perform_standard_attack(attacker)
                elif attacker.class_name == 'Krieger' and attacker.ability_cooldown == 0:
                    shield_amount = 10 + attacker.attributes.get('str', 0)
                    attacker.shield += shield_amount
                    self.combat_log.append({'type': 'shield', 'actor_id': attacker.id, 'actor_name': attacker.class_name, 'shield_amount': shield_amount, 'shield_total': attacker.shield, 'sound': 'Shield_Warrior.mp3', 'player_owner': action_owner})
                    attacker.ability_cooldown = 3
                elif attacker.class_name == 'Magier' and attacker.ability_cooldown == 0:
                    opponent_player = self.player2 if attacker in self.player1.units else self.player1
                    main_target = next((u for u in opponent_player.units if not u.is_defeated and not u.is_hidden), None)
                    if main_target:
                        splash_targets = self._get_adjacent_units(main_target, opponent_player)
                        all_target_ids = [main_target.id] + [t.id for t in splash_targets if t != main_target and not t.is_defeated and not t.is_hidden]
                        self.combat_log.append({'type': 'splash_preview', 'attacker_id': attacker.id, 'target_ids': all_target_ids, 'sound': 'Mage_Fireball.mp3', 'player_owner': action_owner})
                        self._apply_damage(attacker, main_target, attacker.attack)
                        for splash_target in splash_targets:
                            if splash_target != main_target and not splash_target.is_defeated and not splash_target.is_hidden:
                                self._apply_damage(attacker, splash_target, int(attacker.attack * 0.5), is_splash=True)
                        attacker.ability_cooldown = 2
                    else: self._perform_standard_attack(attacker)
                elif attacker.class_name == 'Barde' and attacker.ability_cooldown == 0:
                    self.combat_log.append({'type': 'battle_song', 'actor_id': attacker.id, 'actor_name': attacker.class_name, 'sound': 'Bard_Buff.mp3', 'player_owner': action_owner})
                    for ally in (self.player1.units if attacker in self.player1.units else self.player2.units):
                        if not ally.is_defeated and ally.id != attacker.id and not any(e['type'] == 'battle_song' for e in ally.status_effects):
                            ally.status_effects.append({'type': 'battle_song', 'duration': 3})
                    attacker.ability_cooldown = 3
                elif attacker.class_name == 'Schurke':
                    if attacker.is_hidden:
                        target = next((u for u in (self.player2.units if attacker in self.player1.units else self.player1.units) if not u.is_defeated and not u.is_hidden), None)
                        if target: self._apply_damage(attacker, target, int(attacker.attack * 2.0), ignores_shield=True)
                        attacker.is_hidden = False
                        self.combat_log.append({'type': 'unhide', 'actor_id': attacker.id, 'actor_name': attacker.class_name, 'sound': 'Schurke.mp3', 'player_owner': action_owner})
                    elif attacker.ability_cooldown == 0:
                        attacker.is_hidden = True
                        self.combat_log.append({'type': 'hide', 'actor_id': attacker.id, 'actor_name': attacker.class_name, 'sound': 'Rouge_shadow.mp3', 'player_owner': action_owner})
                        attacker.ability_cooldown = 2
                    else: self._perform_standard_attack(attacker)
                elif attacker.class_name == 'Barbar' and attacker.ability_cooldown == 0:
                    attacker.status_effects.append({'type': 'frenzy', 'duration': 3})
                    self.combat_log.append({'type': 'frenzy_start', 'actor_id': attacker.id, 'actor_name': attacker.class_name, 'sound': 'Barbarian_Warcry.mp3', 'player_owner': action_owner})
                    attacker.ability_cooldown = 4
                else: self._perform_standard_attack(attacker)
                if self.check_game_over(): break
            if self.check_game_over(): break
        self.determine_winner()

    def _apply_damage(self, attacker, target, damage, is_splash=False, ignores_shield=False, sound=None):
        if any(e['type'] == 'frenzy' for e in attacker.status_effects): damage = int(damage * 1.5)
        if any(e['type'] == 'battle_song' for e in attacker.status_effects): damage = int(damage * 1.25)
        if not ignores_shield:
            damage_to_shield = min(target.shield, damage)
            target.shield -= damage_to_shield
            remaining_damage = damage - damage_to_shield
        else: remaining_damage = damage
        target.hp = max(0, target.hp - remaining_damage)
        log_entry = {'type': 'attack', 'attacker_id': attacker.id, 'attacker_name': attacker.class_name, 'target_id': target.id, 'target_name': target.class_name, 'damage': damage, 'target_hp_after': target.hp, 'target_shield_after': target.shield, 'is_splash': is_splash, 'ignores_shield': ignores_shield, 'target_max_hp': target.max_hp, 'player_owner': "player1" if attacker in self.player1.units else "player2"}
        if sound: log_entry['sound'] = sound
        self.combat_log.append(log_entry)
        if target.hp == 0:
            target.is_defeated = True
            defeated_player_owner = "player1" if target in self.player1.units else "player2"
            self.combat_log.append({'type': 'defeated', 'target_id': target.id, 'target_name': target.class_name, 'sound': f"Dying_0{random.randint(1, 3)}.mp3", 'player_owner': defeated_player_owner})

    def determine_winner(self):
        p1_alive = any(not u.is_defeated for u in self.player1.units)
        p2_alive = any(not u.is_defeated for u in self.player2.units)
        if not p2_alive: self.winner = self.player1.name
        elif not p1_alive: self.winner = self.player2.name
        elif self.round_count >= 20:
            p1_hp_pct = sum(u.hp for u in self.player1.units) / sum(u.max_hp for u in self.player1.units) if sum(u.max_hp for u in self.player1.units) > 0 else 0
            p2_hp_pct = sum(u.hp for u in self.player2.units) / sum(u.max_hp for u in self.player2.units) if sum(u.max_hp for u in self.player2.units) > 0 else 0
            if p1_hp_pct > p2_hp_pct: self.winner = self.player1.name
            elif p2_hp_pct > p1_hp_pct: self.winner = self.player2.name
            else: self.winner = "Unentschieden"
        if self.winner == self.player1.name:
            xp_pool = sum(u.cost for u in self.player2.units)
            surviving_units = [u for u in self.player1.units if not u.is_defeated]
            if surviving_units:
                xp_per_survivor = xp_pool // len(surviving_units)
                barracks_ids = {u.id for u in self.player1.barracks}
                for unit in surviving_units:
                    unit.add_xp(xp_per_survivor)
                    unit.is_in_barracks = unit.id in barracks_ids
                    self.survivors.append(unit)

    def resolve_combat_instantly(self):
        p1_dpr = sum(u.attack for u in self.player1.units)
        p2_dpr = sum(u.attack for u in self.player2.units)
        p1_total_hp = sum(u.hp for u in self.player1.units)
        p2_total_hp = sum(u.hp for u in self.player2.units)

        rounds_to_kill_p2 = float('inf')
        if p1_dpr > 0:
            rounds_to_kill_p2 = p2_total_hp / (p1_dpr * random.uniform(0.9, 1.1))

        rounds_to_kill_p1 = float('inf')
        if p2_dpr > 0:
            rounds_to_kill_p1 = p1_total_hp / (p2_dpr * random.uniform(0.9, 1.1))

        if rounds_to_kill_p2 < rounds_to_kill_p1:
            self.winner = self.player1.name
            for u in self.player2.units:
                u.is_defeated = True
        elif rounds_to_kill_p1 < rounds_to_kill_p2:
            self.winner = self.player2.name
            for u in self.player1.units:
                u.is_defeated = True
        else:
            self.winner = "Unentschieden"

        self.combat_log.append({'type': 'quick_combat_result', 'winner': self.winner})

    def check_game_over(self): return not any(not u.is_defeated for u in self.player1.units) or not any(not u.is_defeated for u in self.player2.units)
    def _get_adjacent_units(self, target_unit, opponent_player):
        if not target_unit.position: return []
        r, c = map(int, target_unit.position.split(','))
        adjacent_positions = [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]
        return [opponent_player.board.get(f"{r_adj},{c_adj}") for r_adj, c_adj in adjacent_positions if opponent_player.board.get(f"{r_adj},{c_adj}")]

def generate_random_unit():
    attributes = {'str': random.randint(8, 15), 'dex': random.randint(8, 15), 'con': random.randint(8, 15), 'int': random.randint(8, 15), 'wis': random.randint(8, 15), 'cha': random.randint(8, 15)}
    return Unit(attributes=attributes)

SAVE_FILE = "game_data.json"
def save_data(player):
    with open(SAVE_FILE, "w") as f: json.dump(player.to_dict(), f, indent=4)
def load_data():
    if not os.path.exists(SAVE_FILE): return None
    try:
        with open(SAVE_FILE, "r") as f:
            data = json.load(f)
            return Player.from_dict(data)
    except (json.JSONDecodeError, KeyError): return None

app = Flask(__name__)
app.secret_key = os.urandom(24)
CLASS_ICONS = {'Krieger': '⚔️', 'Schurke': '🏹', 'Barbar': '🪓', 'Magier': '🔮', 'Kleriker': '✨', 'Barde': '🎵', 'Abenteurer': '🧑‍'}

def get_game_from_session():
    game_data = session.get('game')
    if game_data:
        game = Game()
        game.player1 = Player.from_dict(game_data.get('player1'))
        game.player2 = Player.from_dict(game_data.get('player2'))
        game.game_state = game_data.get('game_state', 'title_screen')
        game.shop_units = [Unit.from_dict(u) for u in game_data.get('shop_units', [])]
        game.round_count = game_data.get('round_count', 0)
        game.winner = game_data.get('winner')
        game.survivors = [Unit.from_dict(s) for s in game_data.get('survivors', [])]
        return game
    return Game()

def save_game_to_session(game):
    session['game'] = {
        'player1': game.player1.to_dict(),
        'player2': game.player2.to_dict(),
        'game_state': game.game_state,
        'shop_units': [u.to_dict() for u in game.shop_units],
        'round_count': game.round_count,
        'winner': game.winner,
        'survivors': [s.to_dict() for s in game.survivors],
    }

@app.route('/')
def index():
    game = get_game_from_session()
    # If the game is finished, we show the title screen but preserve the game state
    # until a new game is started. This prevents wiping combat results.
    if game.game_state == "finished":
        game.game_state = "title_screen"
        save_game_to_session(game)

    save_exists = os.path.exists(SAVE_FILE)
    return render_template('index.html', game=game, save_exists=save_exists, class_icons=CLASS_ICONS)

@app.route('/start_game', methods=['POST'])
def start_game():
    game = Game()
    player_data = load_data()
    if player_data:
        game.player1 = player_data
    game.game_state = "preparation"
    game.shop_units = [generate_random_unit() for _ in range(4)]
    save_game_to_session(game)
    return redirect(url_for('index'))

@app.route('/new_game', methods=['POST'])
def new_game():
    if os.path.exists(SAVE_FILE):
        os.remove(SAVE_FILE)
    game = Game()
    game.game_state = "preparation"
    game.shop_units = [generate_random_unit() for _ in range(4)]
    save_game_to_session(game)
    return redirect(url_for('index'))

@app.route('/buy_unit/<unit_id>', methods=['POST'])
def buy_unit(unit_id):
    game = get_game_from_session()
    unit_to_buy = next((u for u in game.shop_units if u.id == unit_id), None)
    if unit_to_buy and game.player1.gold >= unit_to_buy.cost:
        slot = next((pos for pos, unit in game.player1.board.items() if unit is None), None)
        if slot:
            game.player1.gold -= unit_to_buy.cost
            game.player1.units.append(unit_to_buy)
            game.player1.board[slot] = unit_to_buy
            game.shop_units.remove(unit_to_buy)
            game.shop_units.append(generate_random_unit())
            save_game_to_session(game)
    return redirect(url_for('index'))

@app.route('/deploy_unit/<unit_id>', methods=['POST'])
def deploy_unit(unit_id):
    game = get_game_from_session()
    unit_to_deploy = next((u for u in game.player1.barracks if u.id == unit_id), None)
    slot = request.form.get('slot')
    if unit_to_deploy and not any(u.id == unit_id for u in game.player1.units) and slot and slot in game.player1.board and game.player1.board[slot] is None:
        deployed_unit = Unit.from_dict(unit_to_deploy.to_dict())
        deployed_unit.from_barracks = True
        deployed_unit.position = slot
        game.player1.units.append(deployed_unit)
        game.player1.board[slot] = deployed_unit
        game.player1.barracks = [u for u in game.player1.barracks if u.id != unit_id]
        save_game_to_session(game)
        save_data(game.player1) # Also save persistent barracks data
    return redirect(url_for('index'))

@app.route('/return_to_barracks/<unit_id>', methods=['POST'])
def return_to_barracks(unit_id):
    game = get_game_from_session()
    unit_to_return = next((u for u in game.player1.units if u.id == unit_id), None)
    if unit_to_return:
        game.player1.units = [u for u in game.player1.units if u.id != unit_id]
        for pos, unit in game.player1.board.items():
            if unit and unit.id == unit_id:
                game.player1.board[pos] = None
                break
        if not any(u.id == unit_id for u in game.player1.barracks):
            game.player1.barracks.append(unit_to_return)

        save_game_to_session(game)
        save_data(game.player1) # Also save persistent barracks data
    return redirect(url_for('index'))

@app.route('/start_combat', methods=['POST'])
def start_combat():
    game = get_game_from_session()
    ai_player = game.player2
    if not ai_player.units:
        candidate_units = sorted([generate_random_unit() for _ in range(10)], key=lambda u: u.cost)
        for unit_to_buy in candidate_units:
            if len(ai_player.units) >= 6 or ai_player.gold < unit_to_buy.cost: break
            slot = next((pos for pos, unit in ai_player.board.items() if unit is None), None)
            if slot:
                ai_player.gold -= unit_to_buy.cost
                unit_to_buy.position = slot
                ai_player.units.append(unit_to_buy)
                ai_player.board[slot] = unit_to_buy
            else: break

    combat_type = request.form.get('combat_type')
    is_quick_combat = combat_type == 'quick'
    if is_quick_combat:
        game.resolve_combat_instantly()
        game.determine_winner() # Centralize winner determination
        session['show_animation'] = False
    else:
        game.run_full_combat()
        session['show_animation'] = True

    game.game_state = "finished"
    save_game_to_session(game)
    return redirect(url_for('combat_results'))

@app.route('/combat_results')
def combat_results():
    game = get_game_from_session()
    # The check `if game.game_state != "finished":` was too strict and caused a redirect loop.
    # The page should be accessible as long as the session was populated by /start_combat.
    show_animation = session.get('show_animation', False)
    combat_log_json = json.dumps(game.combat_log)

    return render_template('combat_replay.html',
                           game=game,
                           combat_log_json=combat_log_json,
                           show_animation=show_animation,
                           class_icons=CLASS_ICONS,
                           winner=game.winner,
                           survivors=game.survivors)

@app.route('/move_to_barracks/<unit_id>', methods=['POST'])
def move_to_barracks(unit_id):
    game = get_game_from_session()
    player_data = load_data() # Barracks are persistent
    if not player_data:
        player_data = Player(name="Spieler 1")

    survivor = next((u for u in game.survivors if u.id == unit_id), None)
    if survivor:
        is_existing = any(u.id == survivor.id for u in player_data.barracks)

        if is_existing:
             # Find and update the existing unit
            for i, u in enumerate(player_data.barracks):
                if u.id == survivor.id:
                    player_data.barracks[i] = survivor
                    break
            flash(f"Einheit '{survivor.nickname or survivor.class_name}' aktualisiert.", "success")
        elif len(player_data.barracks) < 3:
            player_data.barracks.append(survivor)
            flash(f"Einheit '{survivor.nickname or survivor.class_name}' in die Kaserne verschoben.", "success")
        else:
            flash("Die Kaserne ist voll! Einheit kann nicht hinzugefügt werden.", "error")
            return redirect(url_for('combat_results'))

        game.survivors = [s for s in game.survivors if s.id != unit_id]
        save_data(player_data)
        save_game_to_session(game)

    return redirect(url_for('combat_results'))

@app.route('/level_up_unit/<unit_id>', methods=['POST'])
def level_up_unit(unit_id):
    player_data = load_data()
    if not player_data:
        return redirect(url_for('barracks'))
    unit_to_level_up = next((u for u in player_data.barracks if u.id == unit_id), None)
    if unit_to_level_up:
        if unit_to_level_up.level_up_if_possible():
            save_data(player_data)
    return redirect(url_for('barracks'))


@app.route('/barracks')
def barracks():
    player_data = load_data()
    if not player_data:
        player_data = Player(name="Spieler 1")
    return render_template('barracks.html', player=player_data, class_icons=CLASS_ICONS)

@app.route('/rename_unit/<unit_id>', methods=['POST'])
def rename_unit(unit_id):
    player_data = load_data()
    if not player_data:
        return redirect(url_for('barracks'))

    unit_to_rename = next((u for u in player_data.barracks if u.id == unit_id), None)

    if unit_to_rename:
        new_name = request.form.get('nickname')
        unit_to_rename.nickname = new_name
        save_data(player_data)

    return redirect(url_for('barracks'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)