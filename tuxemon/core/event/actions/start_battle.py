# -*- coding: utf-8 -*-
#
# Tuxemon
# Copyright (c) 2014-2017 William Edwards <shadowapex@gmail.com>,
#                         Benjamin Bean <superman2k5@gmail.com>
#
# This file is part of Tuxemon
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import logging

from tuxemon.core import tools
from tuxemon.core import db
from tuxemon.core.combat import check_battle_legal
from tuxemon.core.event.eventaction import EventAction
from tuxemon.core.platform import mixer

logger = logging.getLogger(__name__)


class StartBattleAction(EventAction):
    """ Start a battle and switch to the combat module. The parameters must
    contain an NPC slug in the NPC database.

    Valid Parameters: npc_slug

    **Examples:**

    >>> action.__dict__
    {
        "type": "start_battle",
        "parameters": [
            "npc_hiker1"
        ]
    }

    """
    name = "start_battle"
    valid_parameters = [
        (str, "npc_slug")
    ]

    def start(self):
        player = self.session.player

        # Don't start a battle if we don't even have monsters in our party yet.
        if not check_battle_legal(player):
            logger.debug("battle is not legal, won't start")
            return False

        world = self.session.control.get_state_name("WorldState")
        if not world:
            return False

        # Stop movement and keypress on the server.
        if self.session.control.isclient or self.session.control.ishost:
            self.session.control.client.update_player(player.facing, event_type="CLIENT_START_BATTLE")

        npc = world.get_entity(self.parameters.npc_slug)
        npc.load_party()

        # Lookup the environment
        env_db = db.JSONDatabase()
        env_db.load("environment")
        env_slug = "grass"
        if 'environment' in player.game_variables:
            env_slug = player.game_variables['environment']
        env = env_db.lookup(env_slug, table="environment")

        # Add our players and setup combat
        logger.debug("Starting battle!")
        self.session.control.push_state("CombatState", players=(player, npc), combat_type="trainer", graphics=env['battle_graphics'])

        # Start some music!
        filename = env['battle_music']
        mixer.music.load(tools.transform_resource_filename('music', filename))
        mixer.music.play(-1)
        if self.session.control.current_music["song"]:
            self.session.control.current_music["previoussong"] = self.session.control.current_music["song"]
        self.session.control.current_music["status"] = "playing"
        self.session.control.current_music["song"] = filename

    def update(self):
        if self.session.control.get_state_name("CombatState") is None:
            self.stop()
