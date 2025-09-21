import uuid
from flask import Flask, render_template, redirect, url_for

import random

# --- DATA CLASSES ---
class Unit:
    def __init__(self, name, hp, attack, initiative, cost):
        self.id = str(uuid.uuid4())
        self.name = name
        self.hp = hp
        self.max_hp = hp
        self.attack = attack
        self.initiative = initiative
        self.cost = cost
        self.is_defeated = False
        self.position = None

    def __repr__(self):
        return f"{self.name} (HP: {self.hp}/{self.max_hp})"

class Player:
    def __init__(self, name, is_ai=False):
        self.name = name
        self.is_ai = is_ai
        self.gold = 100 # Starting gold
        self.units = []
        self.board = {(r, c): None for r in range(3) for c in range(2)} # 3 rows, 2 columns

    def place_unit(self, unit, position):
        if self.board.get(position) is None:
            unit.position = position
            self.board[position] = unit
            return True
        return False

    def find_first_available_slot(self):
        for r in range(3):
            for c in range(2):
                if self.board.get((r,c)) is None:
                    return (r,c)
        return None

class Game:
    def __init__(self, player1, player2):
        self.player1 = player1
        self.player2 = player2
        self.players = [player1, player2]
        self.turn_order = []
        self.current_turn_index = 0
        self.game_state = "title_screen" # title_screen, preparation, combat, finished
        self.shop_units = []
        self.round_count = 0
        self.combat_log = []
        self.winner = None

    def start_combat(self):
        all_units = [u for p in self.players for u in p.units]
        self.turn_order = sorted(all_units, key=lambda u: u.initiative, reverse=True)
        self.game_state = "combat"
        self.current_turn_index = 0

    def get_current_attacker(self):
        if not self.turn_order: return None
        return self.turn_order[self.current_turn_index]

    def execute_turn(self):
        """
        Executes a single attack for the current unit and returns a structured log entry.
        """
        if self.game_state != "combat":
            return None

        attacker = self.get_current_attacker()
        if attacker.is_defeated:
            return None

        # Determine opponent
        opponent_player = self.player2 if attacker in self.player1.units else self.player1

        # Find first available target
        target = None
        for r in range(3):
            for c in range(2):
                unit = opponent_player.board.get((r, c))
                if unit and not unit.is_defeated:
                    target = unit
                    break
            if target:
                break

        if target:
            damage = attacker.attack
            target.hp -= damage
            if target.hp <= 0:
                target.hp = 0
                target.is_defeated = True

            return {
                'type': 'attack',
                'attacker_id': attacker.id,
                'attacker_name': attacker.name,
                'target_id': target.id,
                'target_name': target.name,
                'damage': damage,
                'target_hp_after': target.hp,
                'defeated': target.is_defeated
            }

        return {'type': 'info', 'message': f"{attacker.name} hat kein Ziel gefunden."}

    def check_game_over(self):
        """Checks if all units of a player are defeated."""
        p1_units = [u for u in self.player1.units]
        p2_units = [u for u in self.player2.units]

        if not p1_units or not p2_units: return True

        p1_all_defeated = all(u.is_defeated for u in p1_units)
        p2_all_defeated = all(u.is_defeated for u in p2_units)

        return p1_all_defeated or p2_all_defeated

    def run_full_combat(self):
        """Runs the entire combat automatically and logs the results."""
        self.start_combat()

        while self.round_count < 20:
            self.round_count += 1
            self.combat_log.append({'type': 'round', 'number': self.round_count})

            for i in range(len(self.turn_order)):
                self.current_turn_index = i
                action = self.execute_turn()
                if action:
                    self.combat_log.append(action)

                if self.check_game_over():
                    self.game_state = "finished"
                    self.determine_winner()
                    return

        self.game_state = "finished"
        self.determine_winner()

    def _calculate_total_hp_percentage(self, player):
        """Calculates the total percentage of HP remaining for a player."""
        if not player.units:
            return 0

        total_current_hp = sum(u.hp for u in player.units)
        total_max_hp = sum(u.max_hp for u in player.units)

        if total_max_hp == 0:
            return 0

        return (total_current_hp / total_max_hp) * 100

    def determine_winner(self):
        """Determines the winner and stores a JSON-serializable representation."""
        p1_units_alive = any(not u.is_defeated for u in self.player1.units)
        p2_units_alive = any(not u.is_defeated for u in self.player2.units)

        winner_obj = None
        if not p1_units_alive:
            winner_obj = self.player2
        elif not p2_units_alive:
            winner_obj = self.player1
        elif self.round_count >= 20:
            p1_hp_pct = self._calculate_total_hp_percentage(self.player1)
            p2_hp_pct = self._calculate_total_hp_percentage(self.player2)

            # This log message should be a dictionary too, for consistency
            self.combat_log.append({'type': 'info', 'message': "Rundenlimit erreicht! Der Gewinner wird durch die verbleibenden Lebenspunkte bestimmt."})
            self.combat_log.append({'type': 'info', 'message': f"{self.player1.name}: {p1_hp_pct:.2f}% HP | {self.player2.name}: {p2_hp_pct:.2f}% HP"})

            if p1_hp_pct > p2_hp_pct:
                winner_obj = self.player1
            elif p2_hp_pct > p1_hp_pct:
                winner_obj = self.player2
            else:
                self.winner = "Unentschieden"

        if winner_obj:
            self.winner = {'name': winner_obj.name}

# --- UNIT GENERATION ---
UNIT_NAMES = ["Goblin", "Orc", "Elf", "Dwarf", "Knight", "Mage", "Rogue", "Golem"]

def generate_random_unit():
    """Generates a new random unit with balanced stats and a cost."""
    name = random.choice(UNIT_NAMES)
    hp = random.randint(50, 100)
    attack = random.randint(10, 25)
    initiative = random.randint(1, 10)

    # Cost is a simple sum of stats
    cost = int((hp / 5) + attack + initiative)

    return Unit(name, hp, attack, initiative, cost)

# --- GAME SETUP ---
def setup_game():
    """Creates a new, empty game, ready for the title screen."""
    p1 = Player(name="Spieler 1")
    p2 = Player(name="PC", is_ai=True)
    new_game = Game(p1, p2)
    return new_game

# --- FLASK APP ---
app = Flask(__name__)
game = None # Global game state

@app.route('/')
def index():
    global game
    if game is None:
        game = setup_game()
    return render_template('index.html', game=game)

def pc_shopping_ai(player, shop_units):
    """A simple AI for the PC to buy and place units."""
    if not player.is_ai:
        return

    can_afford_something = True
    while can_afford_something:
        can_afford_something = False
        # Find the most expensive unit the AI can afford
        best_buy = None
        for unit in shop_units:
            if player.gold >= unit.cost:
                if best_buy is None or unit.cost > best_buy.cost:
                    best_buy = unit
                    can_afford_something = True

        if best_buy:
            # Buy the unit
            slot = player.find_first_available_slot()
            if slot:
                player.gold -= best_buy.cost
                player.units.append(best_buy)
                player.place_unit(best_buy, slot)
                shop_units.remove(best_buy)
            else:
                # No space left on board
                break

@app.route('/start_game', methods=['POST'])
def start_game():
    """Prepares the game for the shopping phase."""
    global game
    game = setup_game() # Reset the game to a clean state
    game.game_state = "preparation"
    # Populate the shop with 5 random units
    game.shop_units = [generate_random_unit() for _ in range(5)]

    # PC opponent does its shopping
    pc_shopping_ai(game.player2, game.shop_units)

    return redirect(url_for('index'))

@app.route('/buy_unit/<unit_id>', methods=['POST'])
def buy_unit(unit_id):
    """Handles the player buying a unit from the shop."""
    if game and game.game_state == "preparation":
        player = game.player1

        # Find the unit in the shop
        unit_to_buy = next((u for u in game.shop_units if u.id == unit_id), None)

        if unit_to_buy and player.gold >= unit_to_buy.cost:
            # Check if there is space on the board
            slot = player.find_first_available_slot()
            if slot:
                # Process purchase
                player.gold -= unit_to_buy.cost
                player.units.append(unit_to_buy)
                player.place_unit(unit_to_buy, slot)
                game.shop_units.remove(unit_to_buy)

    return redirect(url_for('index'))

@app.route('/start_combat', methods=['POST'])
def start_combat():
    """Runs the combat and renders the replay screen."""
    if game and game.game_state == "preparation":
        # Run the simulation
        game.run_full_combat()
        # Render the replay template with the results
        return render_template('combat_replay.html', game=game, combat_log_json=game.combat_log)
    return redirect(url_for('index'))

@app.route('/new_game', methods=['POST'])
def new_game():
    global game
    game = setup_game()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
