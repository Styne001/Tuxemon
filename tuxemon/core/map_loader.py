# -*- coding: utf-8 -*-
#
# Tuxemon
# Copyright (C) 2014, William Edwards <shadowapex@gmail.com>,
#                     Benjamin Bean <superman2k5@gmail.com>
#
# This file is part of Tuxemon.
#
# Tuxemon is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Tuxemon is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Tuxemon.  If not, see <http://www.gnu.org/licenses/>.
#
# Contributor(s):
#
# William Edwards <shadowapex@gmail.com>
# Leif Theden <leif.theden@gmail.com>
#
#
# core.map Game map module.
#
#
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import logging
from itertools import product

import natsort
import pytmx

from tuxemon.core.event import EventObject
from tuxemon.core.event import MapAction
from tuxemon.core.event import MapCondition
from tuxemon.core.event.eventaction import EventAction
from tuxemon.core.event.eventcondition import EventCondition
from tuxemon.core.map import Map
from tuxemon.core.tools import round_to_divisible, split_escaped, snap_point, snap_rect, tiles_inside_aabb

logger = logging.getLogger(__name__)


def parse_behav_string(behav_string):
    words = behav_string.split(' ', 1)
    behav_type = words[0]
    if len(words) > 1:
        args = split_escaped(words[1])
    else:
        args = list()
    return behav_type, args


class TMXMapLoader(object):
    """Maps are loaded from standard tmx files created from a map editor like Tiled. Events and
    collision regions are loaded and put in the appropriate data structures for the game to
    understand.

    **Tiled:** http://www.mapeditor.org/

    """

    def load(self, filename):
        """Load map data from a tmx map file and get all the map's events and collision areas.
        Loading the map data is done using the pytmx library.

        Specifications for the TMX map format can be found here:
        https://github.com/bjorn/tiled/wiki/TMX-Map-Format

        The list of tiles is structured in a way where you can access an individual tile by
        index number.

        The collision map is a set of (x,y) coordinates that the player cannot walk
        through. This set is generated based on collision regions defined in the
        map file.

        **Examples:**

        In each map, there are three types of objects: **collisions**, **conditions**, and
        **actions**. Here is how an action would be defined using the Tiled map editor:

        .. image:: images/map/map_editor_action01.png

        :param filename: The path to the tmx map file to load.
        :type filename: String

        :rtype: None
        """
        map = Map()
        data = pytmx.TiledMap(filename)
        tile_size = data.tilewidth, data.tileheight

        # Load all objects from the map file and sort them by their type.
        for obj in data.objects:
            if obj.type == 'collision':
                self.process_region(obj, tile_size)
                # collision_map[collision_tile] = region_conditions

            elif obj.type == 'collision-line':
                self.process_line(obj, tile_size)

            elif obj.type == 'event':
                map.events.append(self.load_event(obj, tile_size))

            elif obj.type == 'init':
                map.inits.append(self.load_event(obj, tile_size))

            elif obj.type == 'interact':
                map.interacts.append(self.load_event(obj, tile_size))

    def process_line(self, line, tile_size):
        """ Identify the tiles on either side of the line and block movement along it

        :param line:
        :param tile_size:
        :return:
        """
        if len(line.points) != 2:
            raise Exception("Error: collision lines must be exactly 2 points")

        point1 = snap_point(line.points[0], tile_size)
        point2 = snap_point(line.points[1], tile_size)
        self.line(point1, point2, tile_size)

    def line(self, point1, point2, tile_size):
        x = point1[0] / tile_size[0]  # same as point2[0] b/c vertical
        line_start = point1[1]
        line_end = point2[1]
        num_tiles_in_line = abs(line_start - line_end) / tile_size[1]
        curr_y = line_start / tile_size[1]
        for i in range(int(num_tiles_in_line)):
            side0 = (x - 1, curr_y - 1)
            side1 = (x, curr_y - 1)
            d = {
                "h": {top: "down", bottom: "up"},
                "v": {left: "right", right: "left"}
            }

            yield side0, side1

    def process_region(self, region, tile_size):
        """ Apply region properties to individual tiles

        Right now our collisions are defined in our tmx file as large regions that the player
        can't pass through. We need to convert these areas into individual tile coordinates
        that the player can't pass through.
        Loop through all of the collision objects in our tmx file.
        The region's bounding box will be snapped to the nearest tile coordinates

        :param region:
        :param tile_size:
        :return:
        """
        region_conditions = {}
        properties_to_merge_with_tiles = ["enter", "exit", "continue"]
        for key in properties_to_merge_with_tiles:
            region_conditions[key] = region.properties[key]

        # Loop through the area of this region and create all
        # the tile coordinates that are inside this region.
        rect = snap_rect(region.x, region.y, region.width, region.height, tile_size)
        for collision_tile in tiles_inside_aabb(rect):
            tile_conditions = dict()
            tile_conditions.update(region_conditions)
            yield collision_tile, region_conditions

    def load_event(self, obj, tile_size):
        """

        :param obj:
        :param tile_size:
        :rtype: EventObject
        """
        conds = []
        acts = []
        x = int(obj.x / tile_size[0])
        y = int(obj.y / tile_size[1])
        w = int(obj.width / tile_size[0])
        h = int(obj.height / tile_size[1])

        # Conditions & actions are stored as Tiled properties.
        # We need to sort them by name, so that "act1" comes before "act2" and so on..
        keys = natsort.natsorted(obj.properties.keys())

        for key, value in natsort.natsorted(obj.items()):
            if key.startswith('cond'):
                condition = EventCondition.from_string(value)
                conds.append(condition)

            elif key.startswith('act'):
                action = EventAction.from_string(value)
                acts.append(action)

        for key in keys:
            if key.startswith('behav'):
                behav_string = obj.properties[key]
                behav_type, args = parse_behav_string(behav_string)
                if behav_type == "talk":
                    conds.insert(0, MapCondition("to_talk", args, x, y, w, h, "is"))
                    acts.insert(0, MapAction("npc_face", [args[0], "player"]))
                else:
                    raise Exception

        # TODO: move this to some post-creation function, as more may be needed
        # add a player_facing_tile condition automatically
        if obj.type == "interact":
            cond_data = MapCondition("player_facing_tile", list(), x, y, w, h, "is")
            logger.debug(cond_data)
            conds.append(cond_data)

        return EventObject(obj.id, obj.name, x, y, w, h, conds, acts)