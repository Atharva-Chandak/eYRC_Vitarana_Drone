#!/usr/bin/env python

"""
Team ID        VD#2373
Theme          Vitarana Drone
Author List    Atharva Chandak, Srujan Deolasse, Naitik Khandelwal, Ayush Agrawal
Filename       Task_6_VD_2373_attitude_controller.py
Functions      imu_callback,drone_command_callback,setpoint_callback,gps_callback,reset,pid
Global Variables None


PID attitude controller of the drone

This python file runs a ROS-node of name attitude_control which controls the roll pitch and yaw angles of the eDrone.
This node publishes and subsribes the following topics:
        PUBLICATIONS            SUBSCRIPTIONS
        /roll_error             /pid_tuning_altitude
        /pitch_error            /pid_tuning_pitch
        /yaw_error              /pid_tuning_roll
        /edrone/pwm             /edrone/imu/data
                                /edrone/drone_command


"""

# Importing the required libraries

import math
import time
import rospy
import tf

# util functions
from Task_6_VD_2373_utils import *


# from pid_tune.msg import PidTune
from sensor_msgs.msg import Imu
from std_msgs.msg import Float32
from vitarana_drone.msg import *


class Edrone:
    """docstring for Edrone"""

    def __init__(self):
        rospy.init_node(
            "attitude_controller"
        )  # initializing ros node with name attitude_controller

        # This corresponds to your current orientation of eDrone in quaternion format. This value must be updated each time in your imu callback
        # [x,y,z,w]
        self.drone_orientation_quaternion = [0.0, 0.0, 0.0, 0.0]

        # This corresponds to your current orientation of eDrone converted in euler angles form.
        # [r,p,y]
        self.drone_orientation_euler = [0.0, 0.0, 0.0]

        # This is the setpoint that will be received from the drone_command in the range from 1000 to 2000
        # [r_setpoint, p_setpoint, y_setpoint]
        self.setpoint_cmd = [1500.0, 1500.0, 1500.0, 1500.0]

        # The setpoint of orientation in euler angles at which you want to stabilize the drone
        # [r_setpoint, p_psetpoint, y_setpoint]
        self.setpoint_euler = [0.0, 0.0, 0.0]

        # Declaring pwm_cmd of message type prop_speed and initializing values
        # Hint: To see the message structure of prop_speed type the following command in the terminal
        # rosmsg show vitarana_drone/prop_speed

        self.pwm_cmd = prop_speed()
        self.pwm_cmd.prop1 = 0.0
        self.pwm_cmd.prop2 = 0.0
        self.pwm_cmd.prop3 = 0.0
        self.pwm_cmd.prop4 = 0.0

        # initial setting of Kp, Kd and ki for [roll, pitch, yaw]. eg: self.Kp[2] corresponds to Kp value in yaw axis
        # after tuning and computing corresponding PID parameters, change the parameters
        self.Kp = [4.2, 4.2, 400]
        self.Ki = [0.2, 0.2, 0]
        self.Kd = [4.5, 4.5, 0]
        self.drone_position=[0,0,0]
        self.subs_setpoint=[0,0,0]

        self.throttle = 0
        self.prev_values = [0.0, 0.0, 0.0]
        self.error = [0.0, 0.0, 0.0]
        self.error_sum = [0.0, 0.0, 0.0]
        self.min_values = [0, 0, 0, 0]
        self.max_values = [1024, 1024, 1024, 1024]
        self.out_roll = 0
        self.out_pitch = 0
        self.out_yaw = 0
       
        # # This is the sample time in which you need to run pid. Choose any time which you seem fit. Remember the stimulation step time is 50 ms
        self.sample_time = 0.060  # in seconds

        # Publishing /edrone/pwm, /roll_error, /pitch_error, /yaw_error
        self.pwm_pub = rospy.Publisher("/edrone/pwm", prop_speed, queue_size=1)
        
        # ------------------------ Other ROS Publishers here-----------------------------------------------------
        # self.roll_pub = rospy.Publisher('/roll_error', Float32, queue_size=1)
        # self.pitch_pub = rospy.Publisher('/pitch_error', Float32, queue_size=1)
        # self.yaw_pub = rospy.Publisher('/yaw_error', Float32, queue_size=1)
        # -----------------------------------------------------------------------------------------------------------

        # Subscribing to /drone_command, imu/data, /pid_tuning_roll, /pid_tuning_pitch, /pid_tuning_yaw
        rospy.Subscriber("/drone_command", edrone_cmd, self.drone_command_callback)
        rospy.Subscriber("/edrone/imu/data", Imu, self.imu_callback)
        rospy.Subscriber("/edrone/setpoint",destination,self.setpoint_callback)
        # ------------------------- Other ROS Subscribers here----------------------------------------------------
        # rospy.Subscriber('/pid_tuning_roll', PidTune, self.roll_set_pid)
        # rospy.Subscriber('/pid_tuning_pitch', PidTune, self.pitch_set_pid)
        # rospy.Subscriber('/pid_tuning_yaw', PidTune, self.yaw_set_pid)
        # ------------------------------------------------------------------------------------------------------------

    # Imu callback function
    # The function gets executed each time when imu publishes /edrone/imu/data
    def imu_callback(self, msg):

        self.drone_orientation_quaternion[0] = msg.orientation.x
        self.drone_orientation_quaternion[1] = msg.orientation.y
        self.drone_orientation_quaternion[2] = msg.orientation.z
        self.drone_orientation_quaternion[3] = msg.orientation.w

    # --------------------Set the remaining co-ordinates of the drone from msg----------------------------------------------
    def drone_command_callback(self, msg):
        self.setpoint_cmd[0] = msg.rcRoll
        self.setpoint_cmd[1] = msg.rcPitch
        self.setpoint_cmd[2] = msg.rcYaw
        self.setpoint_cmd[3] = msg.rcThrottle

    def setpoint_callback(self,msg):
        self.subs_setpoint=[msg.lat, msg.long, msg.alt]     

    def gps_callback(self, msg):
        self.drone_position[0] = msg.latitude
        self.drone_position[1] = msg.longitude
        self.drone_position[2] = msg.altitude

    # ----------------------------Define callback function like roll_set_pid to tune pitch, yaw--------------
    # def roll_set_pid(self, roll):
    #     self.Kp[0] = roll.Kp * 0.06  # This is just for an example. You can change the ratio/fraction value accordingly
    #     self.Ki[0] = roll.Ki * 0.008
    #     self.Kd[0] = roll.Kd * 0.3
   
    # def pitch_set_pid(self, pitch):
    #     self.Kp[1] = pitch.Kp * 0.06  # This is just for an example. You can change the ratio/fraction value accordingly
    #     self.Ki[1] = pitch.Ki * 0.008
    #     self.Kd[1] = pitch.Kd * 0.3
        
    # def yaw_set_pid(self, yaw):
    #     self.Kp[2] = yaw.Kp * 1  # This is just for an example. You can change the ratio/fraction value accordingly
    #     self.Ki[2] = yaw.Ki * 0.0008
    #     self.Kd[2] = yaw.Kd * 0.3
    
    # ----------------------------------------------------------------------------------------------------------------------

    def reset(self):
        pwm=prop_speed()
        pwm.prop1=0
        pwm.prop2=0
        pwm.prop3=0
        pwm.prop4=0
        self.pwm_pub.publish(pwm)

    def pid(self):
        # -----------------------------The PID algorithm --------------------------------------------------------------

        # Steps:
        #   1. Convert the quaternion format of orientation to euler angles
        #   2. Convert the setpoint that is in the range of 1000 to 2000 into angles with the limit from -10 degree to 10 degree in euler angles
        #   3. Compute error in each axis. eg: error[0] = self.setpoint_euler[0] - self.drone_orientation_euler[0], where error[0] corresponds to error in roll...
        #   4. Compute the error (for proportional), change in error (for derivative) and sum of errors (for integral) in each axis. Refer "Understanding PID.pdf" to understand PID equation.
        #   5. Calculate the pid output required for each axis. For eg: calcuate self.out_roll, self.out_pitch, etc.
        #   6. Use this computed output value in the equations to compute the pwm for each propeller. LOOK OUT FOR SIGN (+ or -). EXPERIMENT AND FIND THE CORRECT SIGN
        #   7. Don't run the pid continously. Run the pid only at the a sample time. self.sampletime defined above is for this purpose. THIS IS VERY IMPORTANT.
        #   8. Limit the output value and the final command value between the maximum(0) and minimum(1024)range before publishing. For eg : if self.pwm_cmd.prop1 > self.max_values[1]:
        #                                                                                                                                      self.pwm_cmd.prop1 = self.max_values[1]
        #   8. Update previous errors.eg: self.prev_error[1] = error[1] where index 1 corresponds to that of pitch (eg)
        #   9. Add error_sum to use for integral component

        # Converting quaternion to euler angles
        (
            self.drone_orientation_euler[1],
            self.drone_orientation_euler[0],
            self.drone_orientation_euler[2],
        ) = tf.transformations.euler_from_quaternion(
            [
                self.drone_orientation_quaternion[0],
                self.drone_orientation_quaternion[1],
                self.drone_orientation_quaternion[2],
                self.drone_orientation_quaternion[3],
            ]
        )

        # Convertng the range from 1000 to 2000 in the range of -10 degree to 10 degree for axes
        self.setpoint_euler[0] = (self.setpoint_cmd[0] * 0.02) - 30
        self.setpoint_euler[1] = (self.setpoint_cmd[1] * 0.02) - 30
        self.setpoint_euler[2] = (self.setpoint_cmd[2] * 0.02) - 30

        # Also convert the range of 1000 to 2000 to 0 to 1024 for throttle here itself
        self.throttle = (self.setpoint_cmd[3] * 1.024) - 1024

        # Calculating the error
        self.error[0] = self.setpoint_euler[0] - (
            self.drone_orientation_euler[0] * (180 / math.pi)
        )
        self.error[1] = self.setpoint_euler[1] - (
            self.drone_orientation_euler[1] * (180 / math.pi)
        )
        self.error[2] = self.setpoint_euler[2] - (
            self.drone_orientation_euler[2] * (180 / math.pi)
        )
        self.error_sum[0] = self.error_sum[0] + self.error[0]
        self.error_sum[1] = self.error_sum[1] + self.error[1]
        self.error_sum[2] = self.error_sum[2] + self.error[2]

        # Calculating pid values
        self.out_roll = (
            (self.Kp[0] * self.error[0])
            + (self.Ki[0] * self.error_sum[0])
            + ((self.Kd[0] * (self.error[0] - self.prev_values[0])) / self.sample_time)
        )
        self.out_pitch = (
            (self.Kp[1] * self.error[1])
            + (self.Ki[1] * self.error_sum[1])
            + ((self.Kd[1] * (self.error[1] - self.prev_values[1])) / self.sample_time)
        )
        self.out_yaw = (
            (self.Kp[2] * self.error[2])
            + (self.Ki[2] * self.error_sum[2])
            + ((self.Kd[2] * (self.error[2] - self.prev_values[2])) / self.sample_time)
        )

        # Changing the previous sum value
        self.prev_values[0] = self.error[0]
        self.prev_values[1] = self.error[1]
        self.prev_values[2] = self.error[2]
        # print("YAW err:",self.error[2])
        # Giving pwm values
        self.pwm_cmd.prop1 = (
            self.throttle - self.out_roll + self.out_pitch - self.out_yaw
        )
        self.pwm_cmd.prop2 = (
            self.throttle - self.out_roll - self.out_pitch + self.out_yaw
        )
        self.pwm_cmd.prop3 = (
            self.throttle + self.out_roll - self.out_pitch - self.out_yaw
        )
        self.pwm_cmd.prop4 = (
            self.throttle + self.out_roll + self.out_pitch + self.out_yaw
        )

        self.pwm_cmd.prop1 = limit_value(
            self.pwm_cmd.prop1, self.min_values[0], self.max_values[0]
        )
        self.pwm_cmd.prop2 = limit_value(
            self.pwm_cmd.prop2, self.min_values[1], self.max_values[1]
        )
        self.pwm_cmd.prop3 = limit_value(
            self.pwm_cmd.prop3, self.min_values[2], self.max_values[2]
        )
        self.pwm_cmd.prop4 = limit_value(
            self.pwm_cmd.prop4, self.min_values[3], self.max_values[3]
        )

        self.pwm_pub.publish(self.pwm_cmd)


if __name__ == "__main__":

    e_drone = Edrone()

    r = rospy.Rate(50)  # specify rate in Hz based upon your desired PID sampling time, i.e. if desired sample time is 33ms specify rate as 30Hz
    rospy.on_shutdown(e_drone.reset)
    while not rospy.is_shutdown():
        e_drone.set_yaw()
        e_drone.pid()
        r.sleep()