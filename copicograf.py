#!/usr/bin/python3
from pygcode import Line, GCodeLinearMove, GCodeRapidMove
import math
import random


class Copicograf:
    def __init__(self, conf, gcodes=[]):
        self.conf = conf

        self.gcodes = gcodes

        self.water_tray_x = int(self.conf["trays"]["water"]["x"])
        self.water_tray_y = int(self.conf["trays"]["water"]["y"])

        self.canvas_height = int(self.conf["brushograph"]["canvas_height"])
        self.go_in_tray_lift = int(self.conf["brushograph"]["go_in_tray_lift"])
        self.remove_drops_lift = int(self.conf["brushograph"]["remove_drops_lift"])
        self.move_to_other_shape_lift = int(self.conf["brushograph"]["move_to_other_shape_lift"])

        self.tray_enter_radius = int(self.conf["brushograph"]["tray_enter_radius"])
        self.remove_drops_radius = int(self.conf["brushograph"]["remove_drops_radius"])

        self.offset_y = float(self.conf["brushograph"]["offset_y"])
        self.offset_x = float(self.conf["brushograph"]["offset_x"])
        self.paint_per_run_min = int(self.conf["brushograph"]["paint_per_run_min"])
        self.paint_per_run_max = int(self.conf["brushograph"]["paint_per_run_max"])
        self.randomize_paint_per_run()
        self.result_file = "copicograf.gcode"

        self.prepare_paint_count = int(self.conf["brushograph"]["prepare_paint_count"])

        self.initial_gcode_acc = self.conf["brushograph"]["moves"]["normal"]["acc"]
        self.initial_gcode_feedrate_1 = self.conf["brushograph"]["moves"]["normal"]["feedrate_1"]
        self.initial_gcode_feedrate_2 = self.conf["brushograph"]["moves"]["normal"]["feedrate_2"]

        self.paint_gcode_acc = self.conf["brushograph"]["moves"]["fast"]["acc"]
        self.paint_gcode_feedrate_1 = self.conf["brushograph"]["moves"]["fast"]["feedrate_1"]
        self.paint_gcode_feedrate_2 = self.conf["brushograph"]["moves"]["fast"]["feedrate_2"]

        self.remove_drops_gcode_acc = self.conf["brushograph"]["moves"]["remove_drops"]["acc"]
        self.remove_drops_gcode_feedrate_1 = self.conf["brushograph"]["moves"]["remove_drops"]["feedrate_1"]
        self.remove_drops_gcode_feedrate_2 = self.conf["brushograph"]["moves"]["remove_drops"]["feedrate_2"]

    def randomize_paint_per_run(self):
        # randomize paint per run
        self.paint_per_run = random.randrange(self.paint_per_run_min, self.paint_per_run_max)

        # self.paint_per_run = 300

    # def run_machine(self, gcode_result):

    # p = printcore('/dev/cu.usbserial-2130', 115200)
    # or pass in your own array of gcode lines instead of reading from a file
    # gcode = [i.strip() for i in open(gcode_result)]
    # gcode = gcoder.LightGCode(gcode)

    # startprint silently exits if not connected yet
    # while not p.online:
    #     time.sleep(0.1)

    # p.startprint(gcode)

    def save_gcode(self, result_file):
        gcfh = open(result_file, "w+")
        gcfh.write("\n".join(str(g) for g in self.gcodes))
        gcfh.close()

    def prepare_path(self, gcode_path, color_tray_x, color_tray_y):
        def set_normal_speed():
            self.gcodes.append(self.initial_gcode_acc)
            self.gcodes.append(self.initial_gcode_feedrate_1)
            self.gcodes.append(self.initial_gcode_feedrate_2)

        def set_fast_speed():
            self.gcodes.append(self.paint_gcode_acc)
            self.gcodes.append(self.paint_gcode_feedrate_1)
            self.gcodes.append(self.paint_gcode_feedrate_2)

        def set_remove_drops_speed():
            self.gcodes.append(self.remove_drops_gcode_acc)
            self.gcodes.append(self.remove_drops_gcode_feedrate_1)
            self.gcodes.append(self.remove_drops_gcode_feedrate_2)

        set_normal_speed()
        self.gcodes.append("G90 ; sets absolute positioning")
        self.gcodes.append("G21 ; set units to millimeters")
        self.gcodes.append("M400 ; finish moves")
        self.gcodes.append(GCodeRapidMove(z=self.go_in_tray_lift))
        self.gcodes.append("G28 X Y ; home the X and Y axes only")

        self.dist_painted = 0

        def get_coords_in_tray(tray_x, tray_y):
            """Calculate entering and leaving point of brush in tray."""
            angle = random.uniform(0, 2 * math.pi)
            delta_x = abs(self.tray_enter_radius * math.cos(angle))
            delta_y = abs(self.tray_enter_radius * math.sin(angle))

            first_coords = (0, 0)
            second_coords = (0, 0)

            #########################################################
            # 4 possible ways for brush to enter tray (4 quadrants) #
            #########################################################
            quadrant = random.randrange(4)

            # 1. quadrant
            if quadrant == 0:
                first_coords = (int(tray_x + delta_x), int(tray_y + delta_y))
                second_coords = (int(tray_x - delta_x), int(tray_y - delta_y))

            # 2. quadrant
            if quadrant == 1:
                first_coords = (int(tray_x - delta_x), int(tray_y + delta_y))
                second_coords = (int(tray_x + delta_x), int(tray_y - delta_y))

            # 3. quadrant
            if quadrant == 2:
                first_coords = (int(tray_x - delta_x), int(tray_y - delta_y))
                second_coords = (int(tray_x + delta_x), int(tray_y + delta_y))

            # 4. quadrant
            if quadrant == 3:
                first_coords = (int(tray_x + delta_x), int(tray_y - delta_y))
                second_coords = (int(tray_x - delta_x), int(tray_y + delta_y))

            if first_coords[1] > 1000 or second_coords[1] > 1000:
                print("big second")

            return first_coords, second_coords

        def get_relative_point(tray_x, tray_y, x, y, ratio):
            delta_x = abs(tray_x - x)
            delta_y = abs(tray_y - y)

            x_operator = 1
            if tray_x > x:
                x_operator = -1

            y_operator = 1
            if y < tray_y:
                y_operator = -1

            point_x = int(tray_x + (x_operator * delta_x * ratio))
            point_y = int(tray_y + (y_operator * delta_y * ratio))

            # print('tray x: ', tray_x, ', tray y: ', tray_y,
            #       ', x: ', x, ', y: ', y, ', ratio: ', ratio, ', point x: ', point_x, ', point y: ', point_y)

            return point_x, point_y

        def remove_drops(tray_x, tray_y, x, y):
            dist = calculate_dist(tray_x, tray_y, x + self.offset_x, y + self.offset_y)
            ratioStart = self.tray_enter_radius / dist
            ratioEnb = self.remove_drops_radius / dist

            x1, y1 = get_relative_point(tray_x, tray_y, x + self.offset_x, y + self.offset_y, ratioStart)
            x2, y2 = get_relative_point(tray_x, tray_y, x + self.offset_x, y + self.offset_y, ratioEnb)

            self.gcodes.append(GCodeLinearMove(X=x1, Y=y1))
            self.gcodes.append(GCodeLinearMove(Z=self.remove_drops_lift))
            set_remove_drops_speed()
            self.gcodes.append(GCodeLinearMove(X=x2, Y=y2))
            set_fast_speed()

        def append_go_in_tray(tray_x, tray_y, x, y, num_of_entries=1, remove_drop=True):
            set_fast_speed()
            for i in range(num_of_entries):
                first_coords, second_coords = get_coords_in_tray(tray_x, tray_y)
                if i == 0:
                    if self.move_to_other_shape_lift + self.canvas_height > self.go_in_tray_lift:
                        self.gcodes.append(GCodeRapidMove(Z=self.move_to_other_shape_lift + self.canvas_height))
                    else:
                        self.gcodes.append(GCodeRapidMove(Z=self.go_in_tray_lift))
                else:
                    self.gcodes.append(GCodeRapidMove(Z=self.go_in_tray_lift))

                if first_coords[1] > 1000 or second_coords[1] > 1000:
                    print("napaka")

                self.gcodes.append(GCodeRapidMove(X=first_coords[0], Y=first_coords[1]))
                self.gcodes.append(GCodeRapidMove(Z=-4))
                self.gcodes.append(GCodeRapidMove(X=second_coords[0], Y=second_coords[1]))
                self.gcodes.append(GCodeRapidMove(Z=self.go_in_tray_lift))

            if remove_drop == True:
                remove_drops(tray_x, tray_y, x, y)

            ########################
            # Return where left of #
            ########################
            # self.gcodes.append(GCodeRapidMove(
            #     Z=self.canvas_height + self.move_to_other_shape_lift))

            if self.move_to_other_shape_lift + self.canvas_height > self.go_in_tray_lift:
                self.gcodes.append(GCodeRapidMove(Z=self.move_to_other_shape_lift + self.canvas_height))
            else:
                self.gcodes.append(GCodeRapidMove(Z=self.go_in_tray_lift))

            self.gcodes.append(GCodeRapidMove(X=x + self.offset_x, Y=y + self.offset_y))
            self.gcodes.append(GCodeRapidMove(Z=self.canvas_height))
            set_normal_speed()

        def append_go_for_paint(x, y):
            append_go_in_tray(color_tray_x, color_tray_y, x, y)

            # self.randomize_paint_per_run()

            self.dist_painted = 0

        def wash_the_brush(x, y):
            append_go_in_tray(self.water_tray_x, self.water_tray_y, x, y, 3, False)

        def prepare_paint(x, y):
            append_go_in_tray(color_tray_x, color_tray_y, x, y, self.prepare_paint_count, True)

        def append_first_intermediate_point(first_point_dist, dist, x1, y1, x2, y2):
            full_delta_x = abs(x1 - x2)
            full_delta_y = abs(y1 - y2)

            quotient = first_point_dist / dist

            first_delta_x = full_delta_x * quotient
            first_delta_y = full_delta_y * quotient

            x_operator = 1
            if x1 > x2:
                x_operator = -1

            y_operator = 1
            if y1 > y2:
                y_operator = -1

            first_point_x = int(x1 + (x_operator * first_delta_x))
            first_point_y = int(y1 + (y_operator * first_delta_y))

            self.gcodes.append(GCodeLinearMove(X=first_point_x + self.offset_x, Y=first_point_y + self.offset_y))

            append_go_for_paint(first_point_x, first_point_y)

            return first_point_x, first_point_y

        def append_intermediate_point(previous_point_x, previous_point_y, x2, y2):
            line_dist = self.paint_per_run

            full_delta_x = abs(previous_point_x - x2)
            full_delta_y = abs(previous_point_y - y2)

            rest_dist = calculate_dist(previous_point_x, previous_point_y, x2, y2)

            quotient = line_dist / rest_dist

            delta_x = full_delta_x * quotient
            delta_y = full_delta_y * quotient

            x_operator = 1
            if previous_point_x > x2:
                x_operator = -1

            y_operator = 1
            if previous_point_y > y2:
                y_operator = -1

            new_point_x = previous_point_x + (int(delta_x) * x_operator)
            new_point_y = previous_point_y + (int(delta_y) * y_operator)

            self.gcodes.append(GCodeLinearMove(X=new_point_x + self.offset_x, Y=new_point_y + self.offset_y))

            append_go_for_paint(new_point_x, new_point_y)

            return new_point_x, new_point_y

        def append_intermediate_points(dist, x1, y1, x2, y2):
            first_point_dist = self.paint_per_run - self.dist_painted

            first_point_x, first_point_y = append_first_intermediate_point(first_point_dist, dist, x1, y1, x2, y2)

            long_strokes_dist = dist - first_point_dist
            num_of_long_strokes = int(long_strokes_dist / self.paint_per_run)
            previous_point_x = first_point_x
            previous_point_y = first_point_y

            for i in range(num_of_long_strokes):
                previous_point_x, previous_point_y = append_intermediate_point(previous_point_x, previous_point_y, x2, y2)

            self.gcodes.append(GCodeLinearMove(X=x2 + self.offset_x, Y=y2 + self.offset_y))

            remaining_dist = calculate_dist(previous_point_x, previous_point_y, x2, y2)
            return remaining_dist

        def calculate_dist(x1, y1, x2, y2):
            return math.hypot(x2 - x1, y2 - y1)

        def append_dist_painted(dist):
            self.dist_painted += dist

        def get_linear_moves(line):
            result = []
            for gcode in line.block.gcodes:
                if isinstance(gcode, GCodeRapidMove):
                    result.append(gcode)
                if isinstance(gcode, GCodeLinearMove):
                    result.append(gcode)
            return result

        def get_coords(line):
            moves = get_linear_moves(line)
            for move in moves:
                if move.X is not None and move.Y is not None:
                    return move, line.block.modal_params
            return None, None

        # Mix the color
        prepare_paint(0, 0)

        # Wash the brush in water before starting to paint
        wash_the_brush(0, 0)

        # Go for paint before starting
        append_go_for_paint(0, 0)

        self.last_draw_gcode = None
        self.last_draw_params = None
        self.append_paint_dist = False
        self.lines_painted = 0

        self.brush_on_canvas = False
        self.extruding = False
        self.move_to_other_shape = False

        self.brush_above_canvas_gcode = GCodeRapidMove(Z=self.move_to_other_shape_lift + self.canvas_height)

        self.brush_on_canvas_gcode = GCodeRapidMove(Z=self.canvas_height)

        counter = 0

        self.gcodes.append(self.brush_above_canvas_gcode)
        with open(gcode_path) as fh:
            for line_text in fh.readlines():
                line = None
                try:
                    line = Line(line_text)
                except AssertionError:
                    continue
                text = str(line)
                # print("text: ",text)

                if text.strip() == "G1 F600 Z6" or text.strip() == "G01 Z6 F600":  # G01 Z6 F600
                    # print("going up")
                    self.gcodes.append(self.brush_above_canvas_gcode)
                    self.brush_on_canvas = False

                    set_fast_speed()

                if text.strip() == "G01 Z1 F600" or text.strip() == "G1 F600 Z1":  # G1 F600 Z1
                    # print("going down")
                    # self.gcodes.append(self.brush_on_canvas_gcode)
                    self.brush_on_canvas = True
                    self.move_to_other_shape = True

                if text.strip() == "G92 E0" and self.brush_on_canvas:
                    # print("start extrusion")
                    self.extruding = True
                    self.gcodes.append(self.brush_above_canvas_gcode)
                    set_fast_speed()
                    continue

                gcode, params = get_coords(line)
                if gcode is None:
                    continue

                x = float(gcode.X)
                y = float(gcode.Y)

                if x > 1000 and y > 1000:
                    print("napaka 2, x: ", x, ", y: ", y)

                # print("x: ",x,", y: ",y,", params: ",line.block.modal_params)
                # if len(line.block.modal_params)==1 and get_E_value(params) == 13652.6:
                # print("line ",line)

                if self.brush_on_canvas == True:
                    # if len(line.block.modal_params)==0:
                    #     # print("skip drawing this move")
                    #     continue
                    if self.move_to_other_shape == True:
                        self.move_to_other_shape = False
                        self.last_draw_params = params
                        self.last_draw_gcode = gcode
                        self.gcodes.append(GCodeLinearMove(X=float(x + self.offset_x), Y=float(y + self.offset_y)))
                        self.gcodes.append(self.brush_on_canvas_gcode)
                        set_normal_speed()
                        continue
                    # G92 E0

                    if self.extruding == True:
                        self.extruding = False
                        self.last_draw_params = params
                        self.last_draw_gcode = gcode
                        self.gcodes.append(GCodeLinearMove(X=float(x + self.offset_x), Y=float(y + self.offset_y)))
                        self.gcodes.append(self.brush_on_canvas_gcode)
                        set_normal_speed()
                        continue

                    dist = 0
                    if self.last_draw_gcode is not None:
                        # print("calculate dist")
                        prev_x = self.last_draw_gcode.X
                        prev_y = self.last_draw_gcode.Y
                        dist = calculate_dist(prev_x, prev_y, x, y)

                    ################################
                    # what if line is longer then than self.paint_per_run
                    ################################
                    if dist > self.paint_per_run:
                        dist = append_intermediate_points(dist, prev_x, prev_y, x, y)
                        self.randomize_paint_per_run()
                    else:
                        self.gcodes.append(GCodeLinearMove(X=float(x + self.offset_x), Y=float(y + self.offset_y)))

                    append_dist_painted(dist)

                    if self.dist_painted > self.paint_per_run:
                        # print("go for paint")
                        append_go_for_paint(x, y)
                        self.randomize_paint_per_run()

                    self.last_draw_gcode = gcode
                    self.last_draw_params = params

                if self.brush_on_canvas == False:
                    self.gcodes.append(GCodeLinearMove(X=float(x + self.offset_x), Y=float(y + self.offset_y)))
                    # print("continue")
                    continue

                # print("came here")

                counter += 1
                # if counter>5:
                #     break

        if self.move_to_other_shape_lift + self.canvas_height > self.go_in_tray_lift:
            self.gcodes.append(GCodeRapidMove(Z=self.move_to_other_shape_lift + self.canvas_height))
        else:
            self.gcodes.append(GCodeRapidMove(Z=self.go_in_tray_lift))
        # self.gcodes.append(GCodeRapidMove(
        #     z=self.move_to_other_shape_lift+self.canvas_height))
        self.gcodes.append(GCodeRapidMove(X=0, Y=0))

        wash_the_brush(0, 0)

        ###########################
        # Park the brush in water #
        ###########################
        set_fast_speed()
        if self.move_to_other_shape_lift + self.canvas_height > self.go_in_tray_lift:
            self.gcodes.append(GCodeRapidMove(Z=self.move_to_other_shape_lift + self.canvas_height))
        else:
            self.gcodes.append(GCodeRapidMove(Z=self.go_in_tray_lift))
        # self.gcodes.append(GCodeRapidMove(
        #     Z=self.move_to_other_shape_lift+self.canvas_height))
        self.gcodes.append(GCodeRapidMove(X=self.water_tray_x, Y=self.water_tray_y))
        self.gcodes.append(GCodeRapidMove(Z=0))
        set_normal_speed()
