import unittest
import json
import os
from app import app, Player, Unit, save_data, load_data

class FlaskTestCase(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        # Ensure a clean slate before each test
        if os.path.exists("game_data.json"):
            os.remove("game_data.json")

    def tearDown(self):
        # Clean up the save file after each test
        if os.path.exists("game_data.json"):
            os.remove("game_data.json")

    def test_deploy_unit_from_persistent_barracks(self):
        # 1. Set up the persistent state (the file) BEFORE the request.
        player = Player(name="Spieler 1")
        unit_in_barracks = Unit(attributes={'str': 10, 'dex': 10, 'con': 10, 'int': 10, 'wis': 10, 'cha': 10})
        player.barracks.append(unit_in_barracks)
        save_data(player)
        unit_id = unit_in_barracks.id

        with self.app as client:
            # 2. Start the game. This loads game_data.json into the session.
            client.post('/start_game')

            # 3. Simulate the deployment post request.
            target_slot = "0,1"
            response = client.post(f'/deploy_unit/{unit_id}', data={'slot': target_slot})

            # 4. Assertions
            self.assertEqual(response.status_code, 302)

            # 5. Verify the session state has been updated.
            with client.session_transaction() as session:
                game_after_deploy = session.get('game')
                player1_data = game_after_deploy['player1']
                # Check unit is on the board
                self.assertIsNotNone(player1_data['board'][target_slot])
                self.assertEqual(player1_data['board'][target_slot]['id'], unit_id)
                # Check unit is removed from barracks
                self.assertFalse(any(u['id'] == unit_id for u in player1_data['barracks']))

        # 6. Verify the session state has been updated.
        with client.session_transaction() as session:
            game_after_deploy = session.get('game')
            player1_data = game_after_deploy['player1']
            # Check unit is on the board
            self.assertIsNotNone(player1_data['board'][target_slot])
            self.assertEqual(player1_data['board'][target_slot]['id'], unit_id)
            # Check unit is removed from barracks
            self.assertFalse(any(u['id'] == unit_id for u in player1_data['barracks']))

    def test_return_unit_to_persistent_barracks(self):
        # 1. Set up an empty persistent state for the barracks.
        player = Player(name="Spieler 1")
        save_data(player)

        with self.app as client:
            # 2. Start the game, loading the empty barracks into the session.
            client.post('/start_game')

            # 3. Manually set up the transient state (a unit on the board) in the session.
            # This simulates a unit that was deployed in a previous action.
            unit_on_board = Unit(attributes={'str': 15, 'dex': 5, 'con': 12, 'int': 8, 'wis': 11, 'cha': 7})
            unit_on_board.from_barracks = True # Required for the return button to appear
            unit_id = unit_on_board.id
            slot = "1,2"

            with client.session_transaction() as session:
                game_data = session['game']
                player_data = game_data['player1']
                # Add unit to board and active units list in the session
                player_data['units'].append(unit_on_board.to_dict())
                player_data['board'][slot] = unit_on_board.to_dict()
                session['game'] = game_data

            # 4. Call the endpoint to return the unit.
            response = client.post(f'/return_to_barracks/{unit_id}')

            # 5. Assertions
            self.assertEqual(response.status_code, 302)

            # 6. Verify the session state.
            with client.session_transaction() as session:
                game_after_return = session.get('game')
                player1_data = game_after_return['player1']
                # Check unit is removed from board
                self.assertIsNone(player1_data['board'][slot])
                self.assertFalse(any(u['id'] == unit_id for u in player1_data['units']))
                # Check unit is added to the session's barracks
                self.assertTrue(any(u['id'] == unit_id for u in player1_data['barracks']))

        # 7. Verify the session state.
        with client.session_transaction() as session:
            game_after_return = session.get('game')
            player1_data = game_after_return['player1']
            # Check unit is removed from board
            self.assertIsNone(player1_data['board'][slot])
            self.assertFalse(any(u['id'] == unit_id for u in player1_data['units']))
            # Check unit is added to the session's barracks
            self.assertTrue(any(u['id'] == unit_id for u in player1_data['barracks']))

if __name__ == '__main__':
    unittest.main()