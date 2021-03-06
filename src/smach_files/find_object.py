#!/usr/bin/env python
# coding: utf-8
import rospy, rosparam
from turtlebot_edu.srv import *
from turtlebot_edu.msg import *
from std_msgs.msg import *
from subprocess import Popen
from object_recog.msg import stringArray

import move_op # 移動のため
import size_compare # 物体の大きさを比べるためのソースコードをimport(/smach_files/size_compare.py)

#Global変数
detect_obj = stringArray()
detect_count = 0
trials_num = 10 #試行回数
target_obj_list = []


def Detect_object_name_cb(msg):
    global detect_obj
    global detect_count
    detect_obj = msg.data
    detect_count += 1

def processing(target_obj, option, Now_place):
    global detect_obj
    global detect_count
    global trials_num
    global target_obj_list

    # command_analyzerで既に登録してあるobjectのリストを読み込む
    object_list = rosparam.load_file("/home/sobit-x3/catkin_ws/src/command_analyzer/dataForGPSR/object_list_gpsr.yaml")

    # 各部屋のlocation_listを読み込む
    location_list = rosparam.load_file("/home/sobit-x3/catkin_ws/src/gpsr/config/location_list.yaml")

    # Publisherの生成
    pub_word = rospy.Publisher("/speech_word", String, queue_size=1)
    pub_joint_pose = rospy.Publisher("/joint_goal", dynamixel_pos_id, queue_size=10)
    pub_target_place = rospy.Publisher("/waypoint_nav/move_ctrl", String, queue_size=1)

    #引数（target_obj)が空の場合 #error回避
    if not target_obj:
        rospy.logerr('GPSR : Find_object -> Target Object Empty')
        return 'finish'


    # 頭の向きが平行になるjointを定義
    joint_parallel = dynamixel_pos_id()
    joint_parallel.position = 2048
    joint_parallel.id = 3

    # 頭の向きが下になるjointを定義
    joint_bottom = dynamixel_pos_id()
    joint_bottom.position = 2200
    joint_bottom.id = 3

    # 昇降するjointを定義
    joint_height_up = dynamixel_pos_id()
    joint_height_up.position = 2748
    joint_height_up.id = 1

    # 身長を元に戻すjointを定義
    joint_height_init = dynamixel_pos_id()
    joint_height_init.position = 2048
    joint_height_init.id = 1

    pub_joint_pose.publish(joint_parallel)

    rospy.sleep(3)


    rospy.loginfo('GPSR : Find_object -> target_obj : %s', target_obj)
    rospy.loginfo('GPSR : Find_object -> option : %s', option)
    rospy.loginfo('GPSR : Find_object -> Now_place : %s', Now_place)

    #Popen(['roslaunch', 'object_recog', 'ObjectDetect.launch'])
    rospy.sleep(1)

    trials_count = 0

    if Now_place in location_list[0][0]: #物体認識を行う場所が部屋（例.living_room）
        rospy.loginfo("GPSR : Find_object -> Looking for in " + Now_place)

        location_num = len(location_list[0][0][Now_place]) #その部屋の家具の数
        location_count = 0 # カウント用

        find_flag = False

        while find_flag == False: # target_objが見つかるまでループ
            if location_num == location_count: #移動可能な場所がこれ以上ないのでloopから抜ける(対象物体が見つからなかった)
                rospy.loginfo("location_num == location_count")
                pub_word("I could not find " + str(target_obj) + " in " + str(Now_place) + ".")
                break

            elif location_num > location_count:
                location = location_list[0][0][Now_place][location_count]
                location_count += 1

                pub_word.publish('I will move to '+ location + " in " + Now_place +".")
                rospy.sleep(1)

                # 移動
                while not rospy.is_shutdown():
                    m = move_op.processing(location)
                    if m == "SUCCESS":
                        rospy.loginfo('GPSR : Find_object -> Moving [Arrived]')
                        pub_word.publish("I have arrived at " + location + ".")
                        break
                    else:
                        rospy.loginfo('GPSR : Find_object -> Moving [Moving to %s]', location)
                        rospy.sleep(2)


                # 物体認識処理
                if target_obj in object_list[0][0]:
                    target_obj_list = object_list[0][0][target_obj]["object"]

                elif target_obj not in object_list[0][0]:
                    target_obj_list = [target_obj]

                sub_object_name = rospy.Subscriber("/detect_object_name_array", stringArray, Detect_object_name_cb)

                pub_joint_pose.publish(joint_bottom)

                Popen(['roslaunch', 'object_recog', 'ObjectDetect.launch'])

                while not rospy.is_shutdown(): # object_listに属する物体が検出できるまでループ
                    if trials_count > trials_num:
                        rospy.logwarn('GPSR : Find_object -> could not find %s', target_obj)
                        pub_word.publish('I could not find ' + target_obj + ".")
                        find_flag = False
                        break

                    elif str(detect_obj) == "data: []": # 認識の結果が空
                        rospy.logwarn("GPSR : Find_object -> can not detect objects[%s]", str(trials_count))

                    elif str(detect_obj) != "data: []":
                        # target_obj_list内の物体が見つかった
                        if len(list(set(target_obj_list) & set(detect_obj))) != 0:
                            rospy.loginfo('GPSR : Find_object -> detect ' + target_obj + "(" + str(list(set(target_obj_list) & set(detect_obj))) + ")")
                            pub_word.publish('I found ' + target_obj + ".")
                            find_flag = True
                            break

                        # target_obj_list内の物体が見つからない、タイムアウト
                        elif trials_count > trials_num:
                            rospy.logwarn('GPSR : Find_object -> could not find %s', target_obj)
                            pub_word.publish('I could not find ' + target_obj + ".")
                            find_flag = False
                            break

                        #物体認識中
                        else:
                            rospy.loginfo('GPSR : Find_object -> detecting now[%s]',str(trials_count))
                            pub_word.publish("I'm looking for " + target_obj + ".")

                    rospy.sleep(3)
                    trials_count += 1

                detect_obj = stringArray() # 初期化
                detect_count = 0 # 初期化
                trials_count = 0 # 初期化

                Popen(["rosnode", "kill",  "/pcl_obj_detect"])
                rospy.sleep(3)
                Popen(["rosnode", "kill", "/caffe_obj_classification"])
                rospy.sleep(3)
                Popen(["rosnode", "cleanup"])

        # find_flagのloop終了
        pub_joint_pose.publish(joint_parallel)

        detect_obj = stringArray() # 初期化
        detect_count = 0 # 初期化
        trials_count = 0 # 初期化

        Popen(["rosnode", "kill",  "/pcl_obj_detect"])
        rospy.sleep(3)
        Popen(["rosnode", "kill", "/caffe_obj_classification"])
        rospy.sleep(3)
        Popen(["rosnode", "cleanup"])

        if find_flag == False: return "Not Found"
        elif find_flag == True: return "Found"


    if Now_place not in location_list[0][0]: #物体認識を行う場所が机や棚など定まった場所の場合
        sub_object_name = rospy.Subscriber("/detect_object_name_array", stringArray, Detect_object_name_cb)

        pub_joint_pose.publish(joint_bottom)

        #Now_placeごとのロボットの目線の変更処理
        if Now_place == "kitchen_table" or Now_place == "kitchen table":
            pub_joint_pose.publish(joint_height_up)
            rospy.sleep(3)

        if Now_place == "living_table" or Now_place == "living table":
            joint_living_table = dynamixel_pos_id()
            joint_living_table.position = 1900
            joint_living_table.id = 4
            pub_joint_pose.publish(joint_living_table)
            rospy.sleep(3)

        if Now_place == "side shelf" or Now_place == "side_shelf":
            # 頭の向きが平行になるjointを定義
            joint_side_shelf = dynamixel_pos_id()
            joint_side_shelf.position = 2400
            joint_side_shelf.id = 3
            pub_joint_pose.publish(joint_side_shelf)
            rospy.sleep(3)

        if Now_place == "book shelf" or Now_place == "book_shelf":
            # 頭の向きが平行になるjointを定義
            joint_book_shelf = dynamixel_pos_id()
            joint_book_shelf.position = 2350
            joint_book_shelf.id = 3
            pub_joint_pose.publish(joint_book_shelf)
            rospy.sleep(3)

        if Now_place == "desk":
            pub_joint_pose.publish(joint_height_up)
            rospy.sleep(3)



        Popen(['roslaunch', 'object_recog', 'ObjectDetect.launch'])

        # 引数（target_obj）が物体のカテゴリ名の場合　例. target_obj = "drink"(green_tea)
        if target_obj in object_list[0][0]:
            # yamlで記述したカテゴリ内の物体たちを新たなリストに格納
            target_obj_list = object_list[0][0][target_obj]["object"]
            rospy.loginfo("GPSR : Find_object -> target_obj_list: " + str(target_obj_list))

            if option == "count": # カテゴリの物体の個数を数える場合
                rospy.loginfo("GPSR : Find_object -> Count object")
                while not rospy.is_shutdown():
                    # target_obj_list内の物体が見つからない、タイムアウト
                    if trials_count > trials_num:
                        rospy.logwarn('GPSR : Find_object -> could not find %s', target_obj)
                        pub_word.publish('I could not find ' + target_obj + ".")

                        detect_obj = stringArray() # 初期化
                        detect_count = 0 # 初期化
                        trials_count = 0 # 初期化

                        Popen(["rosnode", "kill",  "/pcl_obj_detect"])
                        rospy.sleep(3)
                        Popen(["rosnode", "kill", "/caffe_obj_classification"])
                        rospy.sleep(3)
                        Popen(["rosnode", "cleanup"])

                        return 'not OK'
                        break

                    # 物体認識の結果が空の場合
                    elif str(detect_obj) == "data: []":
                        rospy.logwarn("GPSR : Find_object -> can not detect objects[%s]",str(trials_count))

                    # target_obj_list内の物体が見つかった
                    elif len(list(set(target_obj_list) & set(detect_obj))) != 0:
                        rospy.loginfo('GPSR : Find_object -> detect ' + target_obj + "(" + str(list(set(target_obj_list) & set(detect_obj))) + ")")
                        pub_word.publish('I found ' + str(len(list(set(target_obj_list) & set(detect_obj)))) + " " + target_obj + ".")

                        detect_obj = stringArray() # 初期化
                        detect_count = 0 # 初期化
                        trials_count = 0 # 初期化

                        Popen(["rosnode", "kill",  "/pcl_obj_detect"])
                        rospy.sleep(3)
                        Popen(["rosnode", "kill", "/caffe_obj_classification"])
                        rospy.sleep(3)
                        Popen(["rosnode", "cleanup"])
                        # 数えた物体の個数を返す
                        return len(list(set(target_obj_list) & set(detect_obj)))
                        break


                    #物体認識中
                    else:
                        rospy.loginfo('GPSR : Find_object -> detecting now[%s]', str(trials_count))
                        pub_word.publish("I'm looking for " + target_obj + ".")
                        #rospy.loginfo("target_obj: " + target_obj)
                        #rospy.loginfo("detect_obj: " + str(detect_obj))

                    rospy.sleep(3)
                    trials_count += 1
                # ----- while文終了 -----#


            else: # 単にカテゴリに属する物体を見つけるだけで良い場合
                while not rospy.is_shutdown():
                    # target_obj_list内の物体が見つからない、タイムアウト
                    if trials_count > trials_num:
                        rospy.logwarn('GPSR : Find_object -> could not find %s', target_obj)
                        pub_word.publish('I could not find ' + target_obj + ".")

                        detect_obj = stringArray() # 初期化
                        detect_count = 0 # 初期化
                        trials_count = 0 # 初期化

                        Popen(["rosnode", "kill",  "/pcl_obj_detect"])
                        rospy.sleep(3)
                        Popen(["rosnode", "kill", "/caffe_obj_classification"])
                        rospy.sleep(3)
                        Popen(["rosnode", "cleanup"])

                        return 'not OK'
                        break

                    # 物体認識の結果が空の場合
                    elif str(detect_obj) == "data: []":
                        rospy.logwarn("GPSR : Find_object -> can not detect objects[%s]",str(trials_count))

                    # target_obj_list内の物体が見つかった
                    elif len(list(set(target_obj_list) & set(detect_obj))) != 0:
                        rospy.loginfo('GPSR : Find_object -> detect ' + target_obj + "(" + str(list(set(target_obj_list) & set(detect_obj))) + ")")
                        pub_word.publish('I found ' + target_obj + ".")
                        detect_obj = stringArray() # 初期化
                        detect_count = 0 # 初期化
                        trials_count = 0 # 初期化

                        Popen(["rosnode", "kill",  "/pcl_obj_detect"])
                        rospy.sleep(3)
                        Popen(["rosnode", "kill", "/caffe_obj_classification"])
                        rospy.sleep(3)
                        Popen(["rosnode", "cleanup"])

                        return 'OK'
                        break

                    #物体認識中
                    else:
                        rospy.loginfo('GPSR : Find_object -> detecting now[%s]',str(trials_count))
                        pub_word.publish("I'm looking for " + target_obj + ".")
                        #rospy.loginfo("target_obj: " + target_obj)
                        #rospy.loginfo("detect_obj: " + str(detect_obj))

                    rospy.sleep(3)
                    trials_count += 1
                # ----- while文終了 -----#

        # 大きい物体を検出する場合
        elif target_obj == "biggest_object" or target_obj == "heaviest_object": # and option == "choose":
            rospy.loginfo("GPSR : Find_object -> detect the biggest object")
            biggest_object_name = size_compare.processing("big") #size_compareは別のファイルで記述してある関数（pclで取った矩形の大きさから物体の大きさを判別する）
            rospy.loginfo("GPSR : Find_object -> the biggest object [%s]", biggest_object_name)

            detect_obj = stringArray() # 初期化
            detect_count = 0 # 初期化
            trials_count = 0 # 初期化

            Popen(["rosnode", "kill",  "/pcl_obj_detect"])
            rospy.sleep(3)
            Popen(["rosnode", "kill", "/caffe_obj_classification"])
            rospy.sleep(3)
            Popen(["rosnode", "cleanup"])

            return "The biggest object is " + biggest_object_name + " ."

        # 小さい物体を検出する場合
        elif target_obj == "smallest_object" or target_obj == "thinnest_object" or target_obj == "lightest_object": # and option == "choose":
            rospy.loginfo("GPSR : Find_object -> detect the smallest object")
            smallest_object_name = size_compare.processing("small")
            rospy.loginfo("GPSR : Find_object -> the smallest object [%s]", smallest_object_name)

            detect_obj = stringArray() # 初期化
            detect_count = 0 # 初期化
            trials_count = 0 # 初期化

            Popen(["rosnode", "kill",  "/pcl_obj_detect"])
            rospy.sleep(3)
            Popen(["rosnode", "kill", "/caffe_obj_classification"])
            rospy.sleep(3)
            Popen(["rosnode", "cleanup"])

            return "The smallest object is " + smallest_object_name + " ."

        # 引数(target_obj)が物体名の場合 例. target_obj = "green_tea"
        else:
            while not rospy.is_shutdown():
                # target_objが見つからない、タイムアウト
                if trials_count > trials_num:
                    rospy.logwarn('GPSR : Find_object -> could not find %s', target_obj)
                    pub_word.publish('I could not find ' + target_obj + ".")
                    detect_obj = stringArray() # 初期化
                    detect_count = 0 # 初期化
                    trials_count = 0 # 初期化

                    Popen(["rosnode", "kill",  "/pcl_obj_detect"])
                    rospy.sleep(3)
                    Popen(["rosnode", "kill", "/caffe_obj_classification"])
                    rospy.sleep(3)
                    Popen(["rosnode", "cleanup"])
                    return 'not OK'
                    break

                # 物体認識の結果が空の場合
                elif str(detect_obj) == "data: []":
                    rospy.logwarn("GPSR : Find_object -> can not detect objects[%s]", str(trials_count))

                # target_objが見つかった
                elif target_obj in detect_obj:
                    rospy.loginfo('GPSR : Find_object -> detect %s', target_obj)
                    pub_word.publish('I found ' + target_obj + ".")
                    detect_obj = stringArray() # 初期化
                    detect_count = 0 # 初期化
                    trials_count = 0 # 初期化

                    Popen(["rosnode", "kill",  "/pcl_obj_detect"])
                    rospy.sleep(3)
                    Popen(["rosnode", "kill", "/caffe_obj_classification"])
                    rospy.sleep(3)
                    Popen(["rosnode", "cleanup"])

                    return 'OK'
                    break

                #物体認識中
                else:
                    rospy.loginfo('GPSR : Find_object -> detecting now[%s]',str(trials_count))
                    pub_word.publish("I'm looking for " + target_obj + ".")
                    #rospy.loginfo("target_obj: " + target_obj)
                    #rospy.loginfo("detect_obj: " + str(detect_obj))

                rospy.sleep(3)
                trials_count += 1
            # ----- while文終了 -----#

        #----- 物体認識終了 -----#
        pub_joint_pose.publish(joint_parallel)

        detect_obj = stringArray() # 初期化
        detect_count = 0 # 初期化
        trials_count = 0 # 初期化

        Popen(["rosnode", "kill",  "/pcl_obj_detect"])
        rospy.sleep(3)
        Popen(["rosnode", "kill", "/caffe_obj_classification"])
        rospy.sleep(3)
        Popen(["rosnode", "cleanup"])

        sub_object_name.unregister()



if __name__ == '__main__':	#この部分は「$ python sub.py」の時には実行される
    print "do processing() @object_recog.py"
    rospy.init_node("find_object_test")

    target = "soy milk"
    option = ""
    Now_place = "living table"
    a = processing(target, option, Now_place)
    print a
