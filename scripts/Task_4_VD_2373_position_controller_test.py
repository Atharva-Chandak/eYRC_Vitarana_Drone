#!/usr/bin/env python

'''
PID position controller for the drone
This node publishes and subsribes the following topics:
        PUBLICATIONS            SUBSCRIPTIONS
        /drone_command          /edrone/gps
                                /edrone/setpoint
'''

# Importing the required libraries
import time
import rospy
import tf
import math

# util functions
from Task_4_VD_2373_utils import *

# from pid_tune.msg import PidTune
from sensor_msgs.msg import Imu, NavSatFix,LaserScan
from std_msgs.msg import Float32
from vitarana_drone.msg import *
from vitarana_drone.srv import Gripper


# util functions
from Task_4_VD_2373_utils import *

class Edrone:
    """docstring for Edrone"""

    def __init__(self):
        
        rospy.init_node("position_controller")  # initializing ros node with name position_controller
       
        # The latitude, longitude and altitude of the drone
        self.drone_position = [0.0, 0.0, 0.0]

        # Format for drone_command
        self.cmd_drone = edrone_cmd()
        self.cmd_drone.rcRoll = 1500
        self.cmd_drone.rcPitch = 1500
        self.cmd_drone.rcYaw = 1500
        self.cmd_drone.rcThrottle = 0

        
        # Initial settings for the values of Kp, Ki and Kd for roll, pitch and throttle
        # self.Kp = [1000000*15, 1000000*15,1000]
        # self.Ki = [0, 0, -0.138]
        # self.Kd = [10000000*11.5, 10000000*11.5, 2300]
        self.Kp = [1000000*17.3, 1000000*17.3,1000]
        self.Ki = [0, 0, -0.138]
        self.Kd = [10000000*15, 10000000*15, 2300]

        self.parcel_setpoints=[19.0007046575, 71.9998955286, 21]
        self.target=[0,0,0]
        self.subscribed_target=[0,0,0]
        self.last_point=[0,0,0]
        self.roll_setpoint_queue=[]
        self.pitch_setpoint_queue=[]
        self.setpoint_changed=False
        
        # -----------------------Add other required variables for pid here ----------------------------------------------
        self.error = [0.0, 0.0, 0.0]
        self.prev_error = [0.0, 0.0, 0.0]
        self.error_sum = [0.0, 0.0, 0.0]
        self.error_diff = [0.0, 0.0, 0.0]

        self.rpt = [0.0, 0.0, 0.0]

        # self.scaling_factor=0.0000451704
        self.min_lat_limit =  0.0000451704 * 1.5
        self.min_long_limit = 0.000047487  * 1.5
        
        # minimum and maximum values for roll, pitch and throttle
        self.min_value = [1375, 1375, 1000]
        self.max_value = [1625, 1625, 2000]

        # Sample time in which pid is run. The stimulation step time is 50 ms
        self.sample_time = 0.060  # in seconds

        #  ROS Publishers
        self.cmd_pub = rospy.Publisher("/drone_command", edrone_cmd, queue_size=1)
        # self.throttle_pub = rospy.Publisher("/throttle_error", Float32, queue_size=1)
        # self.roll_pub = rospy.Publisher('/roll_error', Float32, queue_size=1)
        # self.pitch_pub = rospy.Publisher('/pitch_error', Float32, queue_size=1)
        # self.yaw_pub = rospy.Publisher('/yaw_error', Float32, queue_size=1)
        # self.zero_pub = rospy.Publisher("/zero", Float32, queue_size=1)        

        # ROS Subscribers
        rospy.Subscriber("/edrone/gps", NavSatFix, self.gps_callback)
        rospy.Subscriber("/edrone/setpoint",destination,self.setpoint_callback)

        # ROS Services 
        # rospy.wait_for_service('/edrone/activate_gripper')

        # ------------------------------------------------------------------------------------------------------------

    def gps_callback(self, msg):
            self.drone_position[0] = msg.latitude
            self.drone_position[1] = msg.longitude
            self.drone_position[2] = msg.altitude


    def setpoint_callback(self,msg):
        if msg.lat and msg.long and msg.alt:
            if self.subscribed_target[0] != msg.lat or self.subscribed_target[1] != msg.long or self.subscribed_target[2] != msg.alt:
                self.setpoint_changed=True
                print('setpoint_changed')
                self.roll_setpoint_queue=[]
                self.pitch_setpoint_queue=[]
            else:
                self.setpoint_changed=False
                

            self.subscribed_target[0] = msg.lat
            self.subscribed_target[1] = msg.long
            self.subscribed_target[2] = msg.alt

            self.target[2]=self.subscribed_target[2]        

    # method to break down long distance travels into ~5 meter travels in both roll and pitch direction  
    def create_next_setpoints(self,select_rpt):      
        print("generating...")
        err= ( self.subscribed_target[select_rpt] - self.drone_position[select_rpt] )
        print(select_rpt,err)
        print("int(err/0.0000451704)",int(err/(0.0000451704)))
        if select_rpt==0 and abs(err)>(0.0000451704):
            print("Creating roll path")
            for i in range(1,1+int(abs(err)/(0.0000451704))):
                self.roll_setpoint_queue.append(self.drone_position[0]+i*(0.0000451704) if err>0 else self.drone_position[0]-i*(0.0000451704) )
            self.target[0]=err%((0.0000451704))

        elif select_rpt==1 and abs(err)>(0.000047487):
            print("Creating pitch path")
            for i in range(1,1+int(abs(err)/(0.000047487))):
                self.pitch_setpoint_queue.append(self.drone_position[1]+i*(0.000047487) if err>0 else self.drone_position[1]-i*(0.000047487) ) 
            self.target[1]=err%((0.000047487))
            self.setpoint_changed = False #Backup if self.setpoint_changed is published late
    
    # this is an intermediate method. TODO:Delete this
    def create_next_straight_setpoints(self,select_rpt):      
        print("generating...")
        lat_err = self.subscribed_target[0] - self.drone_position[0] 
        long_err = self.subscribed_target[1] - self.drone_position[1] 
        tan_theta = abs(long_err/lat_err)

        if abs( lat_err ) > abs(long_err):
            if select_rpt==0 and abs(lat_err)>(0.0000451704):
                print("Creating roll path")
                for i in range(1,1+int(abs(lat_err)/(0.0000451704))):
                    self.roll_setpoint_queue.append(self.drone_position[0]+i*(0.0000451704) if lat_err>0 else self.drone_position[0]-i*(0.0000451704) )
                self.target[0]=lat_err%((0.0000451704))

            elif select_rpt==1 and abs(long_err)>(0.000047487):
                print("Creating pitch path")
                for i in range(1,1+int(abs(long_err)/(0.000047487*tan_theta))):
                    self.pitch_setpoint_queue.append(self.drone_position[1]+i*(0.000047487)*tan_theta if long_err>0 else self.drone_position[1]-i*(0.000047487)*tan_theta ) 
                self.target[1]=long_err%((0.000047487))
                self.setpoint_changed = False #Backup if self.setpoint_changed is published late
        else:
            if select_rpt==0 and abs(lat_err)>(0.0000451704):
                print("Creating roll path")
                for i in range(1,1+int(abs(lat_err)/(0.0000451704*tan_theta))):
                    self.roll_setpoint_queue.append(self.drone_position[0]+i*(0.0000451704)*tan_theta if lat_err>0 else self.drone_position[0]-i*(0.0000451704)*tan_theta )
                self.target[0]=lat_err%((0.0000451704))

            elif select_rpt==1 and abs(long_err)>(0.000047487):
                print("Creating pitch path")
                for i in range(1,1+int(abs(long_err)/(0.000047487))):
                    self.pitch_setpoint_queue.append(self.drone_position[1]+i*(0.000047487) if long_err>0 else self.drone_position[1]-i*(0.000047487) ) 
                self.target[1]=long_err%((0.000047487))
                self.setpoint_changed = False #Backup if self.setpoint_changed is published late
      

    # method to break down long distance travels into ~5 meter travels in both roll and pitch direction        
    def create_next_linear_setpoints(self,select_rpt):      
        print("generating...")
        lat_err = self.subscribed_target[0] - self.drone_position[0] 
        long_err = self.subscribed_target[1] - self.drone_position[1] 
        tan_theta = abs(long_err/lat_err)

        if abs( lat_err ) > abs(long_err):
            if abs(lat_err)>(self.min_lat_limit):
                print("Creating roll path")
                for i in range(1,1+int(abs(lat_err)/(self.min_lat_limit))):
                    self.roll_setpoint_queue.append(self.drone_position[0]+i*(self.min_lat_limit) if lat_err>0 else self.drone_position[0]-i*(self.min_lat_limit) )

                print("Creating pitch path")
                for i in range(1,1+int(abs(long_err)/(self.min_long_limit*tan_theta))):
                    self.pitch_setpoint_queue.append(self.drone_position[1]+i*(self.min_long_limit)*tan_theta if long_err>0 else self.drone_position[1]-i*(self.min_long_limit)*tan_theta ) 
                
                self.target[0]=lat_err%((self.min_lat_limit))
                self.target[1]=long_err%((self.min_long_limit*tan_theta))
                self.setpoint_changed = False #Backup if self.setpoint_changed is published late
        else:
            if abs(long_err)>(self.min_long_limit):
                print("Creating roll path")
                for i in range(1,1+int(abs(lat_err)/(self.min_lat_limit*tan_theta))):
                    self.roll_setpoint_queue.append(self.drone_position[0]+i*(self.min_lat_limit)*tan_theta if lat_err>0 else self.drone_position[0]-i*(self.min_lat_limit)*tan_theta )

                print("Creating pitch path")
                for i in range(1,1+int(abs(long_err)/(self.min_long_limit))):
                    self.pitch_setpoint_queue.append(self.drone_position[1]+i*(self.min_long_limit) if long_err>0 else self.drone_position[1]-i*(self.min_long_limit) ) 
                
                self.target[0]=lat_err%((self.min_lat_limit*tan_theta))
                self.target[1]=long_err%((self.min_long_limit))
                self.setpoint_changed = False #Backup if self.setpoint_changed is published late
            
    
    def check_proximity(self):

        if( len(self.roll_setpoint_queue)>0 and abs(self.drone_position[0] - self.roll_setpoint_queue[0])<= 0.000004517): #0.000004517
            self.roll_setpoint_queue.pop(0)

        if( len(self.pitch_setpoint_queue)>0 and abs(self.drone_position[1] - self.pitch_setpoint_queue[0])<= 0.0000047487): #0.000004517
            self.pitch_setpoint_queue.pop(0)


    def pid(self,select_rpt,):
        # self.target = list(target_point)       
        # Calculating the error
        if self.setpoint_changed and select_rpt!=2:
            self.create_next_linear_setpoints(select_rpt)
            
        if select_rpt==0:
            if len(self.roll_setpoint_queue)!=0:
                self.target[0]=self.roll_setpoint_queue[0]
            else:
                self.target[0]=self.subscribed_target[0]

        if select_rpt==1:
            if len(self.pitch_setpoint_queue)!=0:
                self.target[1]=self.pitch_setpoint_queue[0]
            else:
                self.target[1]=self.subscribed_target[1]
        
        self.check_proximity()

        self.error[select_rpt] = ( self.target[select_rpt] - self.drone_position[select_rpt] )

        if not select_rpt:
            print("")
            print("Target",self.target)
            print("Drone_pos",self.drone_position)
            print("errrrrrr",self.error)
            print('roll_setpoint_queue',self.roll_setpoint_queue)
            print('pitch_setpoint_queue',self.pitch_setpoint_queue)


        self.error_sum[select_rpt] = self.error_sum[select_rpt] + self.error[select_rpt]
        self.error_diff[select_rpt] = (self.error[select_rpt] - self.prev_error[select_rpt])


        # Calculating pid values
        self.rpt[select_rpt] = (
            (self.Kp[select_rpt] * self.error[select_rpt])
            + (self.Ki[select_rpt] * self.error_sum[select_rpt]) *
            self.sample_time
            + (self.Kd[select_rpt] *
            (self.error_diff[select_rpt]) / self.sample_time)
        )

        # Changing the previous error values
        self.prev_error[select_rpt] = self.error[select_rpt]

        #------------------------------------------------#
        self.cmd_drone.rcRoll = 1500 + self.rpt[0]
        self.cmd_drone.rcPitch = 1500 + self.rpt[1]
        self.cmd_drone.rcYaw = 1500
        self.cmd_drone.rcThrottle = 1500 + self.rpt[2]

        self.cmd_drone.rcRoll = limit_value(
            self.cmd_drone.rcRoll, self.min_value[0], self.max_value[0]
        )
        self.cmd_drone.rcPitch = limit_value(
            self.cmd_drone.rcPitch, self.min_value[1], self.max_value[1]
        )
        self.cmd_drone.rcThrottle = limit_value(
            self.cmd_drone.rcThrottle, self.min_value[2], self.max_value[2]
        )

        # limiting the values
        self.cmd_drone.rcRoll = limit_value(
            self.cmd_drone.rcRoll, self.min_value[0], self.max_value[0]
        )
        self.cmd_drone.rcPitch = limit_value(
            self.cmd_drone.rcPitch, self.min_value[1], self.max_value[1]
        )
        self.cmd_drone.rcThrottle = limit_value(
            self.cmd_drone.rcThrottle, self.min_value[2], self.max_value[2]
        )

        self.cmd_pub.publish(self.cmd_drone)

        # self.throttle_pub.publish(self.error[2])
        # self.roll_pub.publish(self.error[0])
        # self.pitch_pub.publish(self.error[1])
        # self.zero_pub.publish(0)


        if (self.drone_position[0]-self.last_point[0]>=0.000001) or (self.drone_position[1]-self.last_point[1]>=0.000001) or  (self.drone_position[2]-self.last_point[2]>=0.02): 
            self.last_point=list(self.drone_position)


if __name__ == "__main__":

    e_drone = Edrone()
    r = rospy.Rate(50)  # rate in Hz 

    while not rospy.is_shutdown():

        if all(e_drone.drone_position):# and not e_drone.obstacle_detected_bottom and not  e_drone.obstacle_detected_top :
            print(time.strftime("%H:%M:%S"))
            e_drone.pid(0)
            e_drone.pid(1)
            e_drone.pid(2)

        r.sleep()