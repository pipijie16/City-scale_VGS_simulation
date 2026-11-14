import arcpy
import os
from collections import defaultdict
from arcpy.sa import *
import sys

# Helper function to parse command-line arguments (key-value pairs)
def parse_args(args):
    arg_dict = {}
    for i in range(0, len(args), 2):
        key = args[i].strip('\'"')
        val = args[i+1].strip('\'"') if i + 1 < len(args) else None
        arg_dict[key] = val
    return arg_dict

args = parse_args(sys.argv[1:])

city = args.get('city_name')
intermediate_folder = args.get('intermediate_folder')
height_field = args.get('height_field')

city_basic_data_dir = os.path.join(intermediate_folder, f"{city}_basic_data")
os.makedirs(city_basic_data_dir, exist_ok=True)

workspace = os.path.join(intermediate_folder, "microclimate_simulation/")

projected_buildings_origin = os.path.join(intermediate_folder, "footprint/projected.shp")
projected_buildings = os.path.join(intermediate_folder, "footprint/projected_with_glazing_ratio.shp")

arcpy.CopyFeatures_management(projected_buildings_origin, projected_buildings)

homogeneous_morphology_units_origin = os.path.join(workspace, "homogeneous_morphology_units.shp")
homogeneous_morphology_units = os.path.join(workspace, "homogeneous_morphology_units_with_glazing_ratio.shp")

arcpy.CopyFeatures_management(homogeneous_morphology_units_origin, homogeneous_morphology_units)

spatial_ref = arcpy.Describe(projected_buildings).spatialReference

arcpy.env.overwriteOutput = True
arcpy.env.outputZFlag = "Disabled"
arcpy.env.outputMFlag = "Disabled"

# Save the type of buildings in a set
unique_types = set()

# Calculate morphological parameters
def cal_morphological_parameters():
    if not arcpy.ListFields(projected_buildings, "roof_width"):
        arcpy.AddField_management(projected_buildings, "roof_width", "DOUBLE")
    if not arcpy.ListFields(projected_buildings, "canyon_wid"):
        arcpy.AddField_management(projected_buildings, "canyon_wid", "DOUBLE")
    if not arcpy.ListFields(projected_buildings, "orientatio"):
        arcpy.AddField_management(projected_buildings, "orientatio", "LONG")
    if not arcpy.ListFields(projected_buildings, "Area"):
        arcpy.AddField_management(projected_buildings, "Area", "DOUBLE")
    if not arcpy.ListFields(projected_buildings, "mul_hei_ar"):
        arcpy.AddField_management(projected_buildings, "mul_hei_ar", "DOUBLE")
    if not arcpy.ListFields(projected_buildings, "Class_ID"):
        arcpy.AddField_management(projected_buildings, "Class_ID", "LONG")
    if not arcpy.ListFields(projected_buildings, "ID"):
        arcpy.AddField_management(projected_buildings, "ID", "LONG")

    if arcpy.Exists(projected_buildings):
        print("Repairing building footprint geometries...")
        arcpy.management.RepairGeometry(projected_buildings, "DELETE_NULL")

    # Fill sequential unique IDs (1, 2, 3, ...) for all building features
    with arcpy.da.UpdateCursor(projected_buildings, ["ID"]) as cursor:
        for idx, row in enumerate(cursor, start=1):
            row[0] = idx
            cursor.updateRow(row)

    # Calculate building footprint's area
    arcpy.management.CalculateField(projected_buildings, "Area", "!SHAPE.area!", "PYTHON3", None, "DOUBLE")

    # Multiple building height by building footprint's area
    with arcpy.da.UpdateCursor(projected_buildings, [height_field, "Area", "mul_hei_ar"]) as cursor:
        for row in cursor:
            top_height = row[0]
            shape_area = row[1]
            if top_height is not None and shape_area is not None:
                row[2] = top_height * shape_area
            cursor.updateRow(row)
    
    # Roof width
    metric_type = "WIDTH"
    arcpy.topographic.CalculateMetrics(projected_buildings, metric_type, '#', 'roof_width', '#', '#', '#', '#', '#', '#')

    # Canyon width
    homogeneous_morphology_units_lines = os.path.join(workspace, "homogeneous_morphology_units_lines.shp")
    intervals = os.path.join(workspace, f"{city}_intervals.shp")
    intersect_points = os.path.join(workspace, f"{city}_intersect_points.shp")
    intervals_broken_by_points = os.path.join(workspace, f"{city}_intervals_broken_by_points.shp")
    single_part = os.path.join(workspace, f"{city}_intervals_single_part.shp")
    points_intervals_join = os.path.join(workspace, f"{city}_points_intervals_join.shp")
    final_intervals = os.path.join(workspace, f"{city}_final_intervals.shp")
    summary_join_count_table = os.path.join(workspace, f"{city}_summary_join_count_table.dbf")
    summary_join_count_table2 = os.path.join(workspace, f"{city}_summary_join_count_table2.dbf")
    buildings_intervals_join = os.path.join(workspace, f"{city}_buildings_intervals_join.shp")
    canyon_width_stat_table = os.path.join(workspace, f"{city}_canyon_width_stat_table.dbf")

    arcpy.management.PolygonToLine(homogeneous_morphology_units, homogeneous_morphology_units_lines)
    arcpy.management.GenerateTransectsAlongLines(homogeneous_morphology_units_lines, intervals, "5 Meters", "100 Meters")
    arcpy.analysis.Intersect([projected_buildings, intervals], intersect_points, "ALL", None, "POINT")
    arcpy.analysis.Erase(intervals, projected_buildings, intervals_broken_by_points)
    arcpy.management.MultipartToSinglepart(intervals_broken_by_points, single_part)
    arcpy.analysis.SpatialJoin(single_part, intersect_points, points_intervals_join, "JOIN_ONE_TO_MANY", 
                               "KEEP_ALL", None, None, None, None)
    with arcpy.da.UpdateCursor(points_intervals_join, ["JOIN_FID"]) as cursor:
        for row in cursor:
            if row[0] == -1:
                cursor.deleteRow()

    arcpy.analysis.Statistics(points_intervals_join, summary_join_count_table,
                            [["JOIN_FID", "COUNT"]], "TARGET_FID")
    arcpy.MakeTableView_management(summary_join_count_table, "summary_join_count_table_view")
    arcpy.management.SelectLayerByAttribute("summary_join_count_table_view", "NEW_SELECTION", "FREQUENCY = 2")
    arcpy.management.CopyRows("summary_join_count_table_view", summary_join_count_table2)

    if not arcpy.ListFields(points_intervals_join, "length"):
        arcpy.AddField_management(points_intervals_join, "length", "DOUBLE")
    
    arcpy.management.CalculateField(points_intervals_join, "length", "!SHAPE.length!", "PYTHON3", None, "DOUBLE")
    
    temp_points_intervals_join_layer = "temp_points_intervals_join_layer"
    arcpy.MakeFeatureLayer_management(points_intervals_join, temp_points_intervals_join_layer)
    
    arcpy.management.JoinField(temp_points_intervals_join_layer, "TARGET_FID", summary_join_count_table2, "TARGET_FID", 
                               ["FREQUENCY"])
    
    arcpy.management.SelectLayerByAttribute(temp_points_intervals_join_layer, "NEW_SELECTION", "FREQUENCY = 2 AND length >= 6 AND length <= 75")
    arcpy.management.CopyFeatures(temp_points_intervals_join_layer, final_intervals)
    
    arcpy.analysis.SpatialJoin(projected_buildings, final_intervals, buildings_intervals_join, "JOIN_ONE_TO_MANY", 
                               "KEEP_ALL", None, None, None, None)
    arcpy.analysis.Statistics(buildings_intervals_join, canyon_width_stat_table,
                                [["length", "MEAN"]], "ID")
    
    temp_building_layer = "temp_building_layer"
    arcpy.MakeFeatureLayer_management(projected_buildings, temp_building_layer)

    arcpy.management.JoinField(temp_building_layer, "ID", canyon_width_stat_table, "ID", 
                               ["MEAN_lengt"])
    
    with arcpy.da.UpdateCursor(temp_building_layer, 
                             ["canyon_wid", "MEAN_lengt"]) as cursor:
        for row in cursor:
            row[0] = row[1]  # canyon_wid = MEAN_lengt
            cursor.updateRow(row)

    arcpy.management.DeleteField(projected_buildings, ["MEAN_lengt"])

    # Orientation
    arcpy.cartography.CalculatePolygonMainAngle(projected_buildings, "orientatio", "GRAPHIC")

    with arcpy.da.UpdateCursor(projected_buildings, 
                             ["roof_width"]) as cursor:
        for row in cursor:
            # Set upper limit of roof width to 18 since it might be calculated wrongly
            if row[0] > 18:
                row[0] = 18
            elif row[0] < 4:
                row[0] = 4

            cursor.updateRow(row)

    arcpy.management.Delete(homogeneous_morphology_units_lines)
    arcpy.management.Delete(intervals)
    arcpy.management.Delete(intersect_points)
    arcpy.management.Delete(intervals_broken_by_points)
    arcpy.management.Delete(single_part)
    arcpy.management.Delete(points_intervals_join)
    arcpy.management.Delete(summary_join_count_table)
    arcpy.management.Delete(temp_points_intervals_join_layer)
    arcpy.management.Delete(summary_join_count_table2)
    arcpy.management.Delete(buildings_intervals_join)
    arcpy.management.Delete(canyon_width_stat_table)
    arcpy.management.Delete(temp_building_layer)

    print("Complete calculating morphological parameters.")

cal_morphological_parameters()

# Join homogeneous_morphology_units and projected_buildings to make homogeneous_morphology_units contain buildings' parameters
def join_and_get_parameters_of_building():
    if (not arcpy.ListFields(homogeneous_morphology_units, height_field)) and (not arcpy.ListFields(homogeneous_morphology_units, "roof_width")) and (not arcpy.ListFields(homogeneous_morphology_units, "canyon_wid")) and (not arcpy.ListFields(homogeneous_morphology_units, "orientatio")):
        arcpy.AddField_management(homogeneous_morphology_units, height_field, "DOUBLE")
        arcpy.AddField_management(homogeneous_morphology_units, "roof_width", "DOUBLE")
        arcpy.AddField_management(homogeneous_morphology_units, "canyon_wid", "DOUBLE")
        arcpy.AddField_management(homogeneous_morphology_units, "orientatio", "LONG")

        temp_layer = "temp_homogeneous_layer"
        arcpy.MakeFeatureLayer_management(homogeneous_morphology_units, temp_layer)
        
        arcpy.management.JoinField(temp_layer, "FID_1", projected_buildings, "FID", [height_field, "roof_width", "canyon_wid", "orientatio"])
        
        with arcpy.da.UpdateCursor(temp_layer, 
                                [height_field, "roof_width", "canyon_wid", "orientatio",
                                f"{height_field}_1", "roof_wid_1", "canyon_w_1", "orientat_1"]) as cursor:
            for row in cursor:
                row[0] = row[4]  # height_field = height_field_1
                row[1] = row[5]  # roof_width = roof_wid_1
                row[2] = row[6]  # canyon_wid = canyon_w_1
                row[3] = row[7]  # orientatio = orientat_1
                cursor.updateRow(row)

        arcpy.management.Delete(temp_layer)

    if not arcpy.ListFields(homogeneous_morphology_units, "type"):
        arcpy.AddField_management(homogeneous_morphology_units, "type", "TEXT")
    if not arcpy.ListFields(homogeneous_morphology_units, "glaz_ratio"):
        arcpy.AddField_management(homogeneous_morphology_units, "glaz_ratio", "DOUBLE")

    temp_layer = "temp_homogeneous_layer"
    arcpy.MakeFeatureLayer_management(homogeneous_morphology_units, temp_layer)
    
    arcpy.management.JoinField(temp_layer, "FID_1", projected_buildings, "FID", ["type", "glaz_ratio"])
    
    with arcpy.da.UpdateCursor(temp_layer, 
                             ["type", "glaz_ratio",
                              "type_1", "glaz_rat_1"]) as cursor:
        for row in cursor:
            row[0] = row[2]  # type = type_1
            row[1] = row[3]  # glaz_ratio = glaz_ratio_1
            cursor.updateRow(row)

    arcpy.management.Delete(temp_layer)

    arcpy.management.DeleteField(homogeneous_morphology_units, 
                            ["type_1", "glaz_rat_1"])

    with arcpy.da.SearchCursor(homogeneous_morphology_units, ["type"]) as cursor:
        for row in cursor:
            if row[0]:
                unique_types.add(row[0])

    for type_value in unique_types:
        output_feature = os.path.join(workspace, f"homogeneous_morphology_units_{type_value}.shp")
        if arcpy.Exists(output_feature):
            arcpy.Delete_management(output_feature)
        arcpy.MakeFeatureLayer_management(homogeneous_morphology_units, "temp_type_layer", f"type = '{type_value}'")
        arcpy.CopyFeatures_management("temp_type_layer", output_feature)
        print(f"Exported {output_feature} for type: {type_value}")
        arcpy.Delete_management("temp_type_layer")

    print("Complete joining and getting parameters of buildings.")

join_and_get_parameters_of_building()

# Classification begins
def classify_buildings(homogeneous_morphology_units_type, type_value):
    class_ID = 1

    if not arcpy.ListFields(homogeneous_morphology_units_type, "Class_ID"):
        arcpy.AddField_management(homogeneous_morphology_units_type, "Class_ID", "LONG")

    temp_building_layer = f"temp_building_layer_{type_value}"
    arcpy.MakeFeatureLayer_management(projected_buildings, temp_building_layer, f"type = '{type_value}'")

    # Initialize the value of the field
    with arcpy.da.UpdateCursor(temp_building_layer, ["Class_ID"]) as update_cursor:
        for row in update_cursor:
            row[0] = 0
            update_cursor.updateRow(row)

    dissolve = os.path.join(workspace, f"homogeneous_morphology_units_dissolve_{type_value}.shp")

    if arcpy.Exists(dissolve):
        arcpy.Delete_management(dissolve)

    arcpy.management.Dissolve(
        in_features=homogeneous_morphology_units_type,
        out_feature_class=dissolve,
        multi_part="SINGLE_PART"
    )

    with arcpy.da.SearchCursor(dissolve, ["SHAPE@", "FID"]) as polygon_cursor:
        for polygon in polygon_cursor:
            polygon_shape = polygon[0]
            polygon_id = polygon[1]
            
            arcpy.MakeFeatureLayer_management(temp_building_layer, f"building_layer{polygon_id}")
            arcpy.SelectLayerByLocation_management(f"building_layer{polygon_id}", "WITHIN", polygon_shape)
            arcpy.MakeFeatureLayer_management(homogeneous_morphology_units_type, f"homogeneous_morphology_units_layer{polygon_id}")
            arcpy.SelectLayerByLocation_management(f"homogeneous_morphology_units_layer{polygon_id}", "INTERSECT", polygon_shape)

            building_count = int(arcpy.GetCount_management(f"building_layer{polygon_id}").getOutput(0))

            max_count = building_count - 1

            cluster_output = os.path.join(intermediate_folder, f"merge{polygon_id}_{type_value}.shp")

            try:
                if building_count > 100:
                    arcpy.stats.SpatiallyConstrainedMultivariateClustering(
                        f"homogeneous_morphology_units_layer{polygon_id}", cluster_output, 
                        [height_field, "roof_width", "canyon_wid", "orientatio"], "NUM_FEATURES", None, 1, 100, None, "CONTIGUITY_EDGES_ONLY", None, None, None)
                if building_count <= 100:
                    arcpy.stats.SpatiallyConstrainedMultivariateClustering(
                        f"homogeneous_morphology_units_layer{polygon_id}", cluster_output, 
                        [height_field, "roof_width", "canyon_wid", "orientatio"], "NUM_FEATURES", None, 1, max_count, None, "CONTIGUITY_EDGES_ONLY", None, None, None)

                clusters = defaultdict(list)
                shapes_in_a_whole_polygon = []

                with arcpy.da.SearchCursor(cluster_output, ["SHAPE@", "Cluster_ID"]) as cluster_output_cursor:
                    for cluster in cluster_output_cursor:
                        cluster_shape = cluster[0]
                        cluster_id = cluster[1]
                        clusters[cluster_id].append(cluster_shape)
                        shapes_in_a_whole_polygon.append(cluster_shape)
                
                # Regard points in a whole polygon as a single category if the number of buildings is less than or equal to 5
                if building_count <= 5:
                    merged_shape = shapes_in_a_whole_polygon[0]
                    for shape in shapes_in_a_whole_polygon[1:]:
                        merged_shape = merged_shape.union(shape)
                    arcpy.SelectLayerByLocation_management(f"building_layer{polygon_id}", "WITHIN", merged_shape, selection_type="NEW_SELECTION")
                    
                    with arcpy.da.UpdateCursor(f"building_layer{polygon_id}", ["Class_ID"]) as update_cursor:
                        for row in update_cursor:
                            row[0] = class_ID
                            update_cursor.updateRow(row)

                    class_ID = class_ID + 1
                    arcpy.Delete_management(merged_shape)
                else:
                    for cluster_id, shapes in clusters.items():
                        merged_shape = shapes[0]
                        for shape in shapes[1:]:
                            merged_shape = merged_shape.union(shape)

                        arcpy.SelectLayerByLocation_management(f"building_layer{polygon_id}", "WITHIN", merged_shape, selection_type="NEW_SELECTION")
                        
                        with arcpy.da.UpdateCursor(f"building_layer{polygon_id}", ["Class_ID"]) as update_cursor:
                            for row in update_cursor:
                                row[0] = class_ID
                                update_cursor.updateRow(row)

                        class_ID = class_ID + 1
                        arcpy.Delete_management(merged_shape)

                def check_intersected_features(building_layer, current_geom, current_id, first_class_id, buffer_visited, class_id_updated):
                    if current_id in buffer_visited:
                        return
                    
                    buffer_visited.add(current_id)
                    buffer_0_1m = current_geom.buffer(0.1)

                    arcpy.management.SelectLayerByLocation(building_layer, "INTERSECT", buffer_0_1m, selection_type="NEW_SELECTION")
                    if int(arcpy.management.GetCount(building_layer)[0]) > 1:
                        with arcpy.da.UpdateCursor(building_layer, ['SHAPE@', 'ID', 'Class_ID']) as cursor:
                            for row in cursor:
                                if row[1] != current_id:
                                    if row[2] != first_class_id:
                                        old_class_id = row[2]
                                        row[2] = first_class_id
                                        cursor.updateRow(row)
                                        class_id_updated.add(row[1])
                                        print(f"Updated: {row[1]}'s Class_ID from {old_class_id} to {first_class_id}")

                            # Recursively check the intersected features
                            for row in cursor:
                                intersect_geom = row[0]
                                intersect_id = row[1]

                                # Make the layer consists of buildings in the polygon again
                                arcpy.SelectLayerByLocation_management(f"building_layer{polygon_id}", "WITHIN", polygon_shape, selection_type="NEW_SELECTION")
                                building_layer = f"building_layer{polygon_id}"
                                if intersect_id != current_id and intersect_id not in buffer_visited:
                                    check_intersected_features(building_layer, intersect_geom, intersect_id,
                                                              first_class_id, buffer_visited, class_id_updated)

                buffer_visited = set()
                class_id_updated = set()

                with arcpy.da.UpdateCursor(f"building_layer{polygon_id}", ['SHAPE@', 'ID', 'Class_ID']) as cursor:
                    for row in cursor:
                        building_layer_geom = row[0]
                        building_layer_ID = row[1]
                        if building_layer_ID in class_id_updated:
                            continue
                        first_class_id = row[2]
                        if first_class_id != 0:
                            check_intersected_features(f"building_layer{polygon_id}", building_layer_geom, building_layer_ID,
                                                      first_class_id, buffer_visited, class_id_updated)
                
                # Collect unclassified buildings
                unclassified_buildings = []
                with arcpy.da.SearchCursor(f"building_layer{polygon_id}", ['SHAPE@', 'ID', 'Class_ID']) as cursor:
                    for row in cursor:
                        if row[2] == 0: # Class_ID = 0
                            unclassified_buildings.append((row[0], row[1]))  # (geometry, ID)

                # Assign Class_ID to unclassified buildings
                if unclassified_buildings:
                    print(f"Found {len(unclassified_buildings)} buildings with Class_ID = 0 in polygon {polygon_id}")
                    for building_geom, building_id in unclassified_buildings:
                        arcpy.SelectLayerByLocation_management(f"homogeneous_morphology_units_layer{polygon_id}", "INTERSECT", building_geom, selection_type="NEW_SELECTION")
                        arcpy.SelectLayerByLocation_management(f"building_layer{polygon_id}", "INTERSECT", f"homogeneous_morphology_units_layer{polygon_id}", selection_type="NEW_SELECTION")

                        # Find a valid Class_ID for the unclassified building
                        neighbor_class_id = None
                        with arcpy.da.SearchCursor(f"building_layer{polygon_id}", ['SHAPE@', 'ID', 'Class_ID']) as cursor:
                            for row in cursor:
                                if row[1] != building_id and row[2] != 0:  # Exclude the unclassified building itself and other unclassified buildings
                                    neighbor_class_id = row[2]
                                    break

                        # Update the Class_ID for the unclassified building
                        if neighbor_class_id:
                            with arcpy.da.UpdateCursor(f"building_layer{polygon_id}", ['SHAPE@', 'ID', 'Class_ID']) as update_cursor:
                                for row in update_cursor:
                                    if row[1] == building_id:
                                        row[2] = neighbor_class_id
                                        update_cursor.updateRow(row)
                                        print(f"Assigned Class_ID {neighbor_class_id} to building {building_id}")
                                        break
                        else:
                            print(f"No valid Class_ID found for building {building_id} in polygon {polygon_id}")

            except arcpy.ExecuteError:
                # Regard points in a whole polygon as a single category
                with arcpy.da.UpdateCursor(f"building_layer{polygon_id}", ["Class_ID"]) as update_cursor:
                    for row in update_cursor:
                        row[0] = class_ID
                        update_cursor.updateRow(row)
                class_ID = class_ID + 1

            arcpy.Delete_management(f"building_layer{polygon_id}")
            arcpy.Delete_management(cluster_output)
            arcpy.Delete_management("in_memory")

    class_ids = set()
    with arcpy.da.SearchCursor(temp_building_layer, ["Class_ID"]) as search_cursor:
        for row in search_cursor:
            class_ids.add(row[0])

    sorted_class_ids = sorted(class_ids)
    class_id_map = {old_id: new_id for new_id, old_id in enumerate(sorted_class_ids, start=1)}

    with arcpy.da.UpdateCursor(temp_building_layer, ["Class_ID"]) as update_cursor:
        for row in update_cursor:
            row[0] = class_id_map[row[0]]
            update_cursor.updateRow(row)

    with arcpy.da.UpdateCursor(projected_buildings, ["ID", "Class_ID"]) as update_cursor:
        temp_dict = {row[0]: row[1] for row in arcpy.da.SearchCursor(temp_building_layer, ["ID", "Class_ID"])}
        for row in update_cursor:
            id = row[0]
            if id in temp_dict:
                row[1] = temp_dict[id]
            update_cursor.updateRow(row)

    arcpy.Delete_management(temp_building_layer)
    
    print(f"Done classification for type: {type_value}")

for type_value in unique_types:
    homogeneous_morphology_units_type = os.path.join(workspace, f"homogeneous_morphology_units_{type_value}.shp")
    print(f"Classifying buildings for type: {type_value}")
    classify_buildings(homogeneous_morphology_units_type, type_value)

# Join homogeneous_morphology_units and projected_buildings to get classification results
def join_and_get_classification_results(homogeneous_morphology_units_type, type_value):
    if not arcpy.ListFields(homogeneous_morphology_units, "Class_ID"):
        arcpy.AddField_management(homogeneous_morphology_units_type, "Class_ID", "LONG")

    temp_layer = f"temp_homogeneous_layer_{type_value}"
    arcpy.MakeFeatureLayer_management(homogeneous_morphology_units_type, temp_layer)

    temp_building_layer = f"temp_building_layer_{type_value}"
    arcpy.MakeFeatureLayer_management(projected_buildings, temp_building_layer, f"type = '{type_value}'")

    arcpy.management.JoinField(temp_layer, "FID_1", temp_building_layer, "FID", ["Class_ID"])
    
    with arcpy.da.UpdateCursor(temp_layer, 
                             ["Class_ID", "Class_ID_1"]) as cursor:
        for row in cursor:
            row[0] = row[1]  # Class_ID = Class_ID_1
            cursor.updateRow(row)
    
    arcpy.management.Delete(temp_layer)
    arcpy.management.Delete(temp_building_layer)

    arcpy.management.DeleteField(homogeneous_morphology_units_type, 
                            ["Class_ID_1"])

    print(f"Complete joining and getting classification results for type {type_value}.")

for type_value in unique_types:
    homogeneous_morphology_units_type = os.path.join(workspace, f"homogeneous_morphology_units_{type_value}.shp")
    join_and_get_classification_results(homogeneous_morphology_units_type, type_value)

# Statistic the 3D morphological parameters for each homogeneous morphology unit
def statistic_morphological_parameters(homogeneous_morphology_units_type, type_value):
    classes_table = os.path.join(workspace, f"{city}_classes.dbf")

    temp_building_layer = f"temp_building_layer_{type_value}"
    arcpy.MakeFeatureLayer_management(projected_buildings, temp_building_layer, f"type = '{type_value}'")

    arcpy.analysis.Statistics(temp_building_layer, classes_table,
                            [["mul_hei_ar", "SUM"], ["roof_width", "MEAN"], ["canyon_wid", "MEAN"],
                            ["orientatio", "MEAN"], ["Area", "SUM"], [height_field, "MAX"]],
                            "Class_ID")

    # Add field to store the weighted average building height
    if not arcpy.ListFields(homogeneous_morphology_units_type, "wei_bld_he"):
        arcpy.AddField_management(classes_table, "wei_bld_he", "DOUBLE")
    
    with arcpy.da.UpdateCursor(classes_table, ["SUM_mul_he", "SUM_Area", "wei_bld_he"]) as cursor:
        for row in cursor:
            row[2] = row[0] / row[1]
            cursor.updateRow(row)
            
    # Add field to store the top height of VCWG's control volume
    if not arcpy.ListFields(classes_table, "h_top"):
        arcpy.AddField_management(classes_table, "h_top", "DOUBLE")
    
    # Truncate field name to 10 characters to comply with DBF specification
    max_height_col = f"MAX_{height_field}"[:10]

    with arcpy.da.UpdateCursor(classes_table, [max_height_col, "wei_bld_he", "h_top"]) as cursor:
        for row in cursor:
            max_height = row[0]  # MAX_{height_field}
            weighted_height_3x = row[1] * 3  # wei_bld_he * 3
            row[2] = max(max_height + 1, weighted_height_3x) 
            cursor.updateRow(row)

    # Regard the class less then 10 building as 'Sparsely Built' in LCZ when the height is low and canyon width is large
    with arcpy.da.UpdateCursor(classes_table, ["wei_bld_he", "MEAN_canyo", "FREQUENCY"]) as cursor:
        for row in cursor:
            wei_avg_bld_hei = row[0]
            canyon_wid = row[1]
            frequency = row[2]
            if frequency < 10:
                if wei_avg_bld_hei * 5 < canyon_wid:
                    canyon_wid = 5 * wei_avg_bld_hei
                    row[1] = canyon_wid
                    cursor.updateRow(row)
                elif wei_avg_bld_hei > 2.4 * canyon_wid:
                    canyon_wid = wei_avg_bld_hei / 2.4
                    row[1] = canyon_wid
                    cursor.updateRow(row)

    # Set the upper limit of roof width to 18 since it might be calculated wrongly
    with arcpy.da.UpdateCursor(classes_table, ["MEAN_roof_"]) as cursor:
        for row in cursor:
            roof_width = row[0]
            if roof_width > 18:
                row[0] = 18
                cursor.updateRow(row)

    excel_file = os.path.join(intermediate_folder, f"{city}_basic_data/{city}_classes_of_{type_value}.xlsx")
    
    if os.path.exists(excel_file):
        os.remove(excel_file)
    
    arcpy.conversion.TableToExcel(classes_table, excel_file)

    arcpy.management.Delete(classes_table)
    arcpy.Delete_management(temp_building_layer)

    print(f"Done statistics for type: {type_value}")

for type_value in unique_types:
    homogeneous_morphology_units_type = os.path.join(workspace, f"homogeneous_morphology_units_{type_value}.shp")
    statistic_morphological_parameters(homogeneous_morphology_units_type, type_value)

projected_buildings_with_glazing_ratio = projected_buildings

# Export Building ID to Building Type mapping table
def export_building_id_type_mapping():
    input_buildings = projected_buildings_with_glazing_ratio
    output_excel = os.path.join(intermediate_folder, f"{city}_basic_data/{city}_BuildingID_type_mapping.xlsx")
    
    # Check if required fields exist
    required_fields = ["ID", "type"]
    fields = [f.name for f in arcpy.ListFields(input_buildings)]
    missing = [f for f in required_fields if f not in fields]
    if missing:
        print(f"Warning: Missing fields {missing} in buildings shapefile. Skipping mapping export.")
        return
    
    # Temporary table for export (only ID and type)
    temp_table = "in_memory/building_id_type_table"
    arcpy.management.CopyRows(
        in_rows=input_buildings,
        out_table=temp_table,
        config_keyword='ID "ID" true true false 8 Long 0 8,First,#,{};type "type" true true false 50 Text 0 50,First,#,{}'.format(input_buildings, input_buildings)
    )
    
    # Export to Excel
    if arcpy.Exists(output_excel):
        os.remove(output_excel)
    
    arcpy.conversion.TableToExcel(temp_table, output_excel)
    
    arcpy.management.Delete(temp_table)
    
    print(f"Successfully exported building ID to type mapping: {output_excel}")

# Execute at the end
export_building_id_type_mapping()