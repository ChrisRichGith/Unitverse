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
        # This is a simple factory method to create a Unit from a dictionary
        return Unit(
            unit_id=data.get("id"), name=data.get("name"), level=data.get("level", 1),
            hp=data.get("hp"), attack=data.get("attack"), initiative=data.get("initiative"),
            cost=data.get("cost"), xp=data.get("xp", 0)
        )

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

    def run_full_combat(self):
        """Simulates the entire combat from start to finish."""
        turn_order = sorted(self.player1.units + self.player2.units, key=lambda u: u.initiative, reverse=True)

        for i in range(20): # Max 20 rounds
            self.round_count = i + 1
            self.combat_log.append({'type': 'round', 'number': self.round_count})

            for attacker in turn_order:
                if attacker.is_defeated:
                    continue

                opponent_player = self.player2 if attacker in self.player1.units else self.player1
                # Find a target that is not defeated
                target = next((u for u in opponent_player.units if not u.is_defeated), None)

                if target:
                    damage = attacker.attack
                    target.hp = max(0, target.hp - damage)
                    log_entry = {
                        'type': 'attack', 'attacker_id': attacker.id, 'attacker_name': attacker.name,
                        'target_id': target.id, 'target_name': target.name, 'damage': damage,
                        'target_hp_after': target.hp
                    }
                    if target.hp == 0:
                        target.is_defeated = True
                        log_entry['defeated'] = True
                    self.combat_log.append(log_entry)

                if self.check_game_over():
                    break

            if self.check_game_over():
                break

        self.determine_winner()
        self.game_state = "finished"

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
            for unit in self.player1.units:
                if not unit.is_defeated:
                    unit.xp += 50 # Award XP for surviving
                    self.survivors.append(unit)

# --- UNIT GENERATION ---
UNIT_NAMES = ["Goblin", "Orc", "Elf", "Dwarf", "Knight", "Mage", "Rogue", "Golem"]
def generate_random_unit():
    name = random.choice(UNIT_NAMES)
    hp = random.randint(50, 100)
    attack = random.randint(10, 25)
    initiative = random.randint(1, 10)
    cost = int((hp / 5) + attack + initiative)
    return Unit(name, hp, attack, initiative, cost)

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
            player.barracks = [Unit.from_dict(u_data) for u_data in data.get("barracks", [])]
            return player
        except (json.JSONDecodeError, KeyError):
            return None

# --- FLASK APP ---
app = Flask(__name__)
# For now, we start a new game object each time. Persistence will be added later.
game = Game()

@app.route('/')
def index():
    global game
    # If a game has just finished, reset the global game object to show the title screen
    if game.game_state == "finished":
        game = Game()

    # Logic to check if save file exists for enabling/disabling "Spiel laden"
    save_exists = os.path.exists("game_data.json")
    return render_template('index.html', game=game, save_exists=save_exists)

@app.route('/start_game', methods=['POST'])
def start_game():
    global game
    # When starting a new game, we create a fresh game object,
    # but we immediately load the player's barracks data if it exists.
    game = Game()
    player_data = load_data()
    if player_data:
        game.player1 = player_data

    game.game_state = "preparation"
    game.shop_units = [generate_random_unit() for _ in range(4)]
    return redirect(url_for('index'))

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
            # The shop does not replenish in this new design until the next phase.

    return redirect(url_for('index'))

@app.route('/deploy_unit/<unit_id>', methods=['POST'])
def deploy_unit(unit_id):
    if game.game_state != "preparation":
        return redirect(url_for('index'))

    player = game.player1
    unit_to_deploy = next((u for u in player.barracks if u.id == unit_id), None)

    # Prevent deploying the same unit twice
    is_already_deployed = any(u.id == unit_id for u in player.units)

    if unit_to_deploy and not is_already_deployed:
        slot = next((pos for pos, unit in player.board.items() if unit is None), None)
        if slot:
            # Deploy a copy, keeping the original in the barracks
            deployed_unit = Unit.from_dict(unit_to_deploy.to_dict())
            player.units.append(deployed_unit)
            player.board[slot] = deployed_unit

    return redirect(url_for('index'))

@app.route('/start_combat', methods=['POST'])
def start_combat():
    if game.game_state != "preparation":
        return redirect(url_for('index'))

    # AI gets 4 random units
    ai_player = game.player2
    if not ai_player.units: # Ensure AI gets a team if it doesn't have one
        for _ in range(4):
            slot = next((pos for pos, unit in ai_player.board.items() if unit is None), None)
            if slot:
                new_unit = generate_random_unit()
                ai_player.units.append(new_unit)
                ai_player.board[slot] = new_unit
            else:
                break # AI board is full

    game.run_full_combat()

    return render_template('combat_replay.html', game=game, combat_log_json=json.dumps([log for log in game.combat_log]))

@app.route('/load_game', methods=['POST'])
def load_game():
    global game
    loaded_player = load_data()
    if loaded_player:
        game = Game() # Start a fresh game environment
        game.player1 = loaded_player # Overwrite the default player with the loaded one
    return redirect(url_for('index'))

@app.route('/move_to_barracks/<unit_id>', methods=['POST'])
def move_to_barracks(unit_id):
    if game.game_state != "finished":
        return redirect(url_for('index'))

    survivor = next((u for u in game.survivors if u.id == unit_id), None)
    player = game.player1

    if survivor and len(player.barracks) < 3:
        # Check if a unit with the same ID is already in the barracks
        if not any(u.id == survivor.id for u in player.barracks):
            # Add a clean copy to the barracks
            barracks_copy = Unit.from_dict(survivor.to_dict())
            barracks_copy.hp = barracks_copy.max_hp # Heal the unit

            # Since the survivor is a temporary object from a finished game,
            # we need to update the main player object's barracks
            game.player1.barracks.append(barracks_copy)
            game.survivors.remove(survivor) # Remove from the list of choices
            save_data(game.player1) # Save the player's state

    return render_template('combat_replay.html', game=game, combat_log_json=json.dumps([log for log in game.combat_log]))

@app.route('/barracks')
def barracks():
    # When visiting the barracks, we should always have the latest data from the save file.
    # The 'game' object might be stale if a new game was started.
    player_data = load_data()
    if not player_data:
        player_data = game.player1 # Fallback to the current game's player
    return render_template('barracks.html', player=player_data)

@app.route('/upgrade_unit/<unit_id>', methods=['POST'])
def upgrade_unit(unit_id):
    player = load_data() # Always load fresh data before modifying
    if player:
        unit_to_upgrade = next((u for u in player.barracks if u.id == unit_id), None)
        if unit_to_upgrade:
            xp_needed = unit_to_upgrade.level * 100
            if unit_to_upgrade.xp >= xp_needed:
                unit_to_upgrade.xp -= xp_needed
                unit_to_upgrade.level += 1
                # Apply two random stat boosts
                stats_to_upgrade = ["max_hp", "attack", "initiative"]
                for stat in random.sample(stats_to_upgrade, 2):
                    if stat == "max_hp":
                        unit_to_upgrade.max_hp += 10
                        unit_to_upgrade.hp = unit_to_upgrade.max_hp
                    elif stat == "attack":
                        unit_to_upgrade.attack += 2
                    elif stat == "initiative":
                        unit_to_upgrade.initiative += 1
                save_data(player)
    return redirect(url_for('barracks'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
