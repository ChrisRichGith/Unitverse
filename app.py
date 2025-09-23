import uuid
import json
import os
from flask import Flask, render_template, redirect, url_for
import random

# --- DATA CLASSES ---
class Unit:
    def __init__(self, name, hp, attack, initiative, cost, xp=0, level=1, unit_id=None):
        self.id = unit_id if unit_id else str(uuid.uuid4())
        self.name = name
        self.level = level
        self.hp = hp
        self.max_hp = hp
        self.attack = attack
        self.initiative = initiative
        self.cost = cost
        self.xp = xp
        self.is_defeated = False
        self.position = None

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "level": self.level, "hp": self.hp,
            "max_hp": self.max_hp, "attack": self.attack, "initiative": self.initiative,
            "cost": self.cost, "xp": self.xp
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            unit_id=data.get("id"), name=data.get("name"), level=data.get("level", 1),
            hp=data.get("hp"), attack=data.get("attack"), initiative=data.get("initiative"),
            cost=data.get("cost"), xp=data.get("xp", 0)
        )

    def __repr__(self):
        return f"{self.name} (HP: {self.hp}/{self.max_hp})"

class Player:
    def __init__(self, name, is_ai=False):
        self.name = name
        self.is_ai = is_ai
        self.gold = 100
        self.units = []
        self.barracks = []
        self.board = {(r, c): None for r in range(3) for c in range(2)}

    def to_dict(self):
        return { "name": self.name, "barracks": [u.to_dict() for u in self.barracks] }

    @classmethod
    def from_dict(cls, data):
        player = cls(name=data.get("name"))
        player.barracks = [Unit.from_dict(u_data) for u_data in data.get("barracks", [])]
        return player

    def find_first_available_slot(self):
        for r in range(3):
            for c in range(2):
                if self.board.get((r,c)) is None: return (r,c)
        return None

    def place_unit(self, unit, position):
        if self.board.get(position) is None:
            unit.position = position
            self.board[position] = unit
            return True
        return False

class Game:
    def __init__(self, player1, player2):
        self.player1 = player1
        self.player2 = player2
        self.players = [player1, player2]
        self.turn_order = []
        self.current_turn_index = 0
        self.game_state = "title_screen"
        self.shop_units = []
        self.round_count = 0
        self.combat_log = []
        self.winner = None
        self.survivors = []
        self.ai_survivors = []
        self.deployed_barracks_units = []

    def start_combat(self):
        all_units = self.player1.units + self.player2.units
        self.turn_order = sorted(all_units, key=lambda u: u.initiative, reverse=True)
        self.game_state = "combat"
        self.current_turn_index = 0

    def get_current_attacker(self):
        if not self.turn_order: return None
        return self.turn_order[self.current_turn_index]

    def execute_turn(self):
        if self.game_state != "combat": return None
        attacker = self.get_current_attacker()
        if attacker.is_defeated: return None
        opponent_player = self.player2 if attacker in self.player1.units else self.player1
        target = None
        for r in range(3):
            for c in range(2):
                unit = opponent_player.board.get((r, c))
                if unit and not unit.is_defeated:
                    target = unit
                    break
            if target: break
        if target:
            damage = attacker.attack
            target.hp -= damage
            if target.hp <= 0:
                target.hp = 0
                target.is_defeated = True
            return {
                'type': 'attack', 'attacker_id': attacker.id, 'attacker_name': attacker.name,
                'target_id': target.id, 'target_name': target.name, 'damage': damage,
                'target_hp_after': target.hp, 'defeated': target.is_defeated
            }
        return {'type': 'info', 'message': f"{attacker.name} hat kein Ziel gefunden."}

    def check_game_over(self):
        p1_alive = any(not u.is_defeated for u in self.player1.units)
        p2_alive = any(not u.is_defeated for u in self.player2.units)
        return not p1_alive or not p2_alive

    def run_full_combat(self):
        self.start_combat()
        while self.round_count < 20:
            self.round_count += 1
            self.combat_log.append({'type': 'round', 'number': self.round_count})
            for i in range(len(self.turn_order)):
                self.current_turn_index = i
                action = self.execute_turn()
                if action: self.combat_log.append(action)
                if self.check_game_over():
                    self.game_state = "finished"
                    self.determine_winner()
                    return

        self.game_state = "finished"
        self.determine_winner()

    def _calculate_total_hp_percentage(self, player):
        if not player.units: return 0
        total_current_hp = sum(u.hp for u in player.units)
        total_max_hp = sum(u.max_hp for u in player.units)
        if total_max_hp == 0: return 0
        return (total_current_hp / total_max_hp) * 100

    def determine_winner(self):
        p1_alive = any(not u.is_defeated for u in self.player1.units)
        p2_alive = any(not u.is_defeated for u in self.player2.units)
        winner_obj = None
        if not p1_alive: winner_obj = self.player2
        elif not p2_alive: winner_obj = self.player1
        elif self.round_count >= 20:
            p1_hp_pct = self._calculate_total_hp_percentage(self.player1)
            p2_hp_pct = self._calculate_total_hp_percentage(self.player2)
            self.combat_log.append({'type': 'info', 'message': "Rundenlimit erreicht!"})
            if p1_hp_pct > p2_hp_pct: winner_obj = self.player1
            elif p2_hp_pct > p1_hp_pct: winner_obj = self.player2
            else: self.winner = "Unentschieden"
        if winner_obj:
            self.winner = {'name': winner_obj.name}

        # Award XP and identify survivors for both players
        p1_xp_award = 50 if self.winner != "Unentschieden" and self.winner['name'] == self.player1.name else 10
        p2_xp_award = 50 if self.winner != "Unentschieden" and self.winner['name'] == self.player2.name else 10

        for unit in self.player1.units:
            if not unit.is_defeated:
                unit.xp += p1_xp_award
                self.survivors.append(unit)

        # Identify AI survivors separately for AI barracks management
        ai_survivors = []
        for unit in self.player2.units:
            if not unit.is_defeated:
                unit.xp += p2_xp_award
                ai_survivors.append(unit)

        # This is a temporary list for the AI to process, not for display
        self.ai_survivors = ai_survivors

# --- PERSISTENCE ---
SAVE_FILE = "game_data.json"
def save_data(players_dict):
    data_to_save = {name: p.to_dict() for name, p in players_dict.items()}
    with open(SAVE_FILE, "w") as f:
        json.dump(data_to_save, f, indent=4)

def load_data():
    if not os.path.exists(SAVE_FILE):
        return {"Spieler 1": Player(name="Spieler 1"), "PC": Player(name="PC", is_ai=True)}

    with open(SAVE_FILE, "r") as f:
        try:
            data = json.load(f)
            return {name: Player.from_dict(p_data) for name, p_data in data.items()}
        except (json.JSONDecodeError, KeyError):
            return {"Spieler 1": Player(name="Spieler 1"), "PC": Player(name="PC", is_ai=True)}

# --- UNIT GENERATION ---
UNIT_NAMES = ["Goblin", "Orc", "Elf", "Dwarf", "Knight", "Mage", "Rogue", "Golem"]
def generate_random_unit():
    name = random.choice(UNIT_NAMES)
    hp = random.randint(50, 100)
    attack = random.randint(10, 25)
    initiative = random.randint(1, 10)
    cost = int((hp / 5) + attack + initiative)
    return Unit(name, hp, attack, initiative, cost)

def ai_perform_upgrades(player):
    """Checks for and performs any available upgrades for an AI player."""
    if not player.is_ai:
        return False # No changes made

    upgraded = False
    for unit in player.barracks:
        xp_needed = unit.level * 100
        if unit.xp >= xp_needed:
            upgraded = True
            unit.xp -= xp_needed
            unit.level += 1
            stats_to_upgrade = ["max_hp", "attack", "initiative"]
            upgrades = random.sample(stats_to_upgrade, 2)
            for stat in upgrades:
                if stat == "max_hp":
                    unit.max_hp += 10
                    unit.hp = unit.max_hp # Heal to new max
                elif stat == "attack":
                    unit.attack += 2
                elif stat == "initiative":
                    unit.initiative += 1
    return upgraded

# --- FLASK APP ---
app = Flask(__name__)
players = load_data()
# AI performs its upgrades on load
if ai_perform_upgrades(players['PC']):
    save_data(players)

game = Game(players['Spieler 1'], players['PC'])

@app.route('/')
def index():
    # Pass the main player object to the template for display purposes
    return render_template('index.html', game=game, player1=players['Spieler 1'])

@app.route('/barracks')
def barracks():
    return render_template('barracks.html', player1=players['Spieler 1'])

def ai_select_team(player, shop_units):
    """AI first deploys units from its barracks, then buys from the shop."""
    if not player.is_ai:
        return

    # Deploy from barracks first (strongest first)
    barracks_sorted = sorted(player.barracks, key=lambda u: u.xp, reverse=True)
    for unit in barracks_sorted:
        slot = player.find_first_available_slot()
        if slot:
            # Add a copy to the active units list, don't remove from barracks
            deployed_unit = Unit.from_dict(unit.to_dict())
            player.units.append(deployed_unit)
            player.place_unit(deployed_unit, slot)
        else:
            break # No more space

    # Then, buy from shop
    pc_shopping_ai(player, shop_units)

def pc_shopping_ai(player, shop_units):
    """A simple AI for the PC to buy and place units. (Simplified for debugging)"""
    if not player.is_ai:
        return

    # Continue buying as long as there is gold and space
    while player.find_first_available_slot() is not None:
        bought_a_unit = False
        # Iterate over a copy of the list as we might modify it
        for unit in list(shop_units):
            if player.gold >= unit.cost:
                slot = player.find_first_available_slot()
                if not slot: break # Should not happen due to while loop, but for safety

                # Buy the first affordable unit
                player.gold -= unit.cost
                player.units.append(unit)
                player.place_unit(unit, slot)
                shop_units.remove(unit)
                shop_units.append(generate_random_unit())

                bought_a_unit = True
                break # Break from the for loop to restart the buying process

        # If we went through the whole shop and couldn't afford anything, stop.
        if not bought_a_unit:
            break

@app.route('/start_game', methods=['POST'])
def start_game():
    global game, players
    # Reset human player's in-game state
    p1 = players['Spieler 1']
    p1.units = []
    p1.board = {(r, c): None for r in range(3) for c in range(2)}
    p1.gold = 100

    # Reset AI player's in-game state, but keep its barracks
    p2 = players['PC']
    p2.units = []
    p2.board = {(r, c): None for r in range(3) for c in range(2)}
    p2.gold = 100

    game = Game(p1, p2)
    game.game_state = "preparation"
    game.shop_units = [generate_random_unit() for _ in range(5)]
    # AI selects its full team from barracks and shop
    ai_select_team(game.player2, game.shop_units)
    return redirect(url_for('index'))

@app.route('/deploy_unit/<unit_id>', methods=['POST'])
def deploy_unit(unit_id):
    """Handles the player deploying a unit from the barracks."""
    p1 = players['Spieler 1']
    if game and game.game_state == "preparation":
        unit_to_deploy = next((u for u in p1.barracks if u.id == unit_id), None)
        # Prevent deploying the same unit twice
        if unit_to_deploy and unit_to_deploy.id not in game.deployed_barracks_units:
            slot = p1.find_first_available_slot()
            if slot:
                # Deploy a copy, keeping the original in the barracks
                deployed_unit = Unit.from_dict(unit_to_deploy.to_dict())
                p1.units.append(deployed_unit)
                p1.place_unit(deployed_unit, slot)
                game.deployed_barracks_units.append(unit_to_deploy.id)

    return redirect(url_for('index'))

@app.route('/buy_unit/<unit_id>', methods=['POST'])
def buy_unit(unit_id):
    """Handles the player buying a unit from the shop."""
    p1 = players['Spieler 1']
    if game and game.game_state == "preparation":
        unit_to_buy = next((u for u in game.shop_units if u.id == unit_id), None)
        if unit_to_buy and p1.gold >= unit_to_buy.cost:
            slot = p1.find_first_available_slot()
            if slot:
                p1.gold -= unit_to_buy.cost
                p1.units.append(unit_to_buy)
                p1.place_unit(unit_to_buy, slot)
                game.shop_units.remove(unit_to_buy)
                game.shop_units.append(generate_random_unit())
    return redirect(url_for('index'))

@app.route('/move_to_barracks/<unit_id>', methods=['POST'])
def move_to_barracks(unit_id):
    p1 = players['Spieler 1']
    if game and game.game_state == "finished":
        survivor_to_move = next((u for u in game.survivors if u.id == unit_id), None)
        if survivor_to_move and len(p1.barracks) < 3:
            if not any(u.id == survivor_to_move.id for u in p1.barracks):
                survivor_to_move.hp = survivor_to_move.max_hp
                p1.barracks.append(survivor_to_move)
                save_data(players)
                game.survivors.remove(survivor_to_move)
    # After moving a unit, redirect to the barracks to see the result
    return redirect(url_for('barracks'))

def ai_manage_barracks(player, survivors):
    """Decides which survivors to keep in the barracks for the AI."""
    if not player.is_ai:
        return

    # Add all survivors to a pool with existing barracks units
    pool = player.barracks + survivors
    # Sort by XP, highest first
    pool.sort(key=lambda u: u.xp, reverse=True)
    # Keep the top 3
    player.barracks = pool[:3]

@app.route('/start_combat', methods=['POST'])
def start_combat():
    if game and game.game_state == "preparation":
        game.run_full_combat()
        # After combat, the AI manages its barracks
        ai_player = players['PC']
        ai_manage_barracks(ai_player, game.ai_survivors)
        save_data(players) # Save changes for both players
        return render_template('combat_replay.html', game=game, combat_log_json=game.combat_log, player1=players['Spieler 1'])
    return redirect(url_for('index'))

@app.route('/upgrade_unit/<unit_id>', methods=['POST'])
def upgrade_unit(unit_id):
    """Handles the unit upgrade logic."""
    p1 = players['Spieler 1']
    unit_to_upgrade = next((u for u in p1.barracks if u.id == unit_id), None)
    if unit_to_upgrade:
        xp_needed = unit_to_upgrade.level * 100
        if unit_to_upgrade.xp >= xp_needed:
            unit_to_upgrade.xp -= xp_needed
            unit_to_upgrade.level += 1
            stats_to_upgrade = ["max_hp", "attack", "initiative"]
            upgrades = random.sample(stats_to_upgrade, 2)
            for stat in upgrades:
                if stat == "max_hp":
                    unit_to_upgrade.max_hp += 10
                    unit_to_upgrade.hp += 10
                elif stat == "attack":
                    unit_to_upgrade.attack += 2
                elif stat == "initiative":
                    unit_to_upgrade.initiative += 1
            save_data(players)
    return redirect(url_for('barracks'))

@app.route('/new_game', methods=['POST'])
def new_game():
    global game, players
    players = load_data()
    game = Game(players['Spieler 1'], players['PC'])
    game.game_state = "title_screen"
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
