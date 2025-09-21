import uuid
from flask import Flask, render_template, redirect, url_for

# --- DATA CLASSES ---
class Unit:
    def __init__(self, name, hp, attack, initiative):
        self.id = str(uuid.uuid4())
        self.name = name
        self.hp = hp
        self.max_hp = hp
        self.attack = attack
        self.initiative = initiative
        self.is_defeated = False
        self.position = None

    def __repr__(self):
        return f"{self.name} (HP: {self.hp}/{self.max_hp})"

class Player:
    def __init__(self, name):
        self.name = name
        self.board = {(r, c): None for r in range(3) for c in range(2)}

    def place_unit(self, unit, position):
        if self.board.get(position) is None:
            unit.position = position
            self.board[position] = unit

class Game:
    def __init__(self, player1, player2):
        self.player1 = player1
        self.player2 = player2
        self.players = [player1, player2]
        self.turn_order = []
        self.current_turn_index = 0
        self.game_state = "combat" # Start directly in combat for simplicity

    def start_combat(self):
        all_units = [u for p in self.players for u in p.board.values() if u]
        self.turn_order = sorted(all_units, key=lambda u: u.initiative, reverse=True)
        self.current_turn_index = 0

    def get_current_attacker(self):
        if not self.turn_order: return None
        return self.turn_order[self.current_turn_index]

    def execute_turn(self):
        """Executes a single, simple attack turn."""
        if self.game_state != "combat":
            return

        attacker = self.get_current_attacker()
        if attacker.is_defeated:
            # Skip defeated units
            self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
            return

        # Determine opponent
        attacking_player = self.player1 if attacker in self.player1.board.values() else self.player2
        opponent_player = self.player2 if attacking_player is self.player1 else self.player1

        # Find first available target, respecting rows (front-row protection)
        target = None
        for r in range(3): # Iterate rows 0, 1, 2
            for c in range(2): # Iterate columns 0, 1
                unit = opponent_player.board.get((r, c))
                if unit and not unit.is_defeated:
                    target = unit
                    break # Found a target in this row, stop searching columns
            if target:
                break # Found a target in this row, stop searching rows

        if target:
            # Apply damage
            target.hp -= attacker.attack
            if target.hp <= 0:
                target.hp = 0
                target.is_defeated = True

        # Check for game over
        self.check_game_over()

        # Advance to next turn
        self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)

    def check_game_over(self):
        """Checks if all units of a player are defeated."""
        p1_all_defeated = all(u.is_defeated for u in self.player1.board.values() if u)
        p2_all_defeated = all(u.is_defeated for u in self.player2.board.values() if u)
        if p1_all_defeated or p2_all_defeated:
            self.game_state = "finished"

# --- GAME SETUP ---
def setup_game():
    """Creates a new game with a fixed set of units."""
    p1 = Player(name="Spieler 1")
    p2 = Player(name="PC")

    # Player 1's units
    p1.place_unit(Unit(name="Krieger", hp=100, attack=35, initiative=5), (0, 0))
    p1.place_unit(Unit(name="Bogenschütze", hp=70, attack=40, initiative=7), (2, 1))

    # Player 2's units
    p2.place_unit(Unit(name="Goblin", hp=60, attack=30, initiative=8), (0, 1))
    p2.place_unit(Unit(name="Oger", hp=120, attack=25, initiative=4), (1, 0))

    new_game = Game(p1, p2)
    new_game.start_combat()
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

@app.route('/next_turn', methods=['POST'])
def next_turn():
    if game:
        game.execute_turn()
    return redirect(url_for('index'))

@app.route('/new_game', methods=['POST'])
def new_game():
    global game
    game = setup_game()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
