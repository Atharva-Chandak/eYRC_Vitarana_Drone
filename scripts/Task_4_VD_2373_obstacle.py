#!/usr/bin/env python

'''

Node responsible for avoiding and publishing the setpoint to do so.

This node publishes and subsribes the following topics:
    PUBLICATIONS                SUBSCRIPTIONS                   SERVICES
    /edrone/obstacle_setpoint   /edrone/range_finder_top        /edrone/activate_gripper
                                /edrone/range_finder_bottom

'''


import rospy
import math
import time
import tf
from vitarana_drone.msg import *
from sensor_msgs.msg import Imu, NavSatFix,LaserScan
from vitarana_drone.srv import Gripper

# util functions
from Task_4_VD_2373_utils import *


class Obstacle():

    def __init__(self):

        rospy.init_node('obstacle')

        self.obstacle_detected_bottom=False
        self.obstacle_detected_top=False
        self.parcel_picked=False
        self.parcel_picked_published=False
        
        self.top_sensor_dist=[0,0,0,0,0]
        self.bottom_sensor_dist=None

        self.drone_position=[0,0,0]
        self.last_point=[0,0,0]
        self.stop_coords=[19.0015646575,71.9995,12]
        self.avoiding_setpoint=[]

        self.go_up_counter=0
        self.go_up_setpoint=None
        self.setpoint=[0,0,0]
        self.iterations=0
        self.stopped_at_current_pos=False
        self.current_pos_set=False
        
        self.stray_obstacle=False
        self.avoiding=False
        self.pub_msg=destination()
        self.top_obs=destination()
        self.bottom_obs=destination()
        self.subs_setpoint=[0,0,0]
        self.drone_orientation_quaternion=[0,0,0,0]
        self.drone_orientation_euler=[0,0,0]
        # Publishers
        # self.cmd_pub = rospy.Publisher("/edrone/setpoint", destination, queue_size=1)
        self.setpoint_pub = rospy.Publisher("/edrone/obstacle_setpoint", destination, queue_size=2)


        # Subscribers
        rospy.Subscriber("/edrone/range_finder_top",LaserScan,self.range_finder_top_callback)
        # rospy.Subscriber("/edrone/range_finder_bottom",LaserScan,self.range_finder_bottom_callback)
        rospy.Subscriber("/edrone/gps", NavSatFix, self.gps_callback)
        rospy.Subscriber("/edrone/setpoint",destination,self.setpoint_callback)
        rospy.Subscriber("/edrone/imu/data", Imu, self.imu_callback)

        # Services
        self.gripper = rospy.ServiceProxy('/edrone/activate_gripper',Gripper())


    def gps_callback(self, msg):
        self.drone_position[0] = msg.latitude
        self.drone_position[1] = msg.longitude
        self.drone_position[2] = msg.altitude

    def imu_callback(self, msg):

        self.drone_orientation_quaternion[0] = msg.orientation.x
        self.drone_orientation_quaternion[1] = msg.orientation.y
        self.drone_orientation_quaternion[2] = msg.orientation.z
        self.drone_orientation_quaternion[3] = msg.orientation.w

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
    
    def setpoint_callback(self,msg):
        self.subs_setpoint[0]=msg.lat
        self.subs_setpoint[1]=msg.long
        self.subs_setpoint[2]=msg.alt

    def check_gripper(self):
        try:
            resp=self.gripper(True)
            if str(resp).split(' ')[1] == 'True':
                self.parcel_picked=True
        except Exception as e:
            print("check_gripper",e)


    def check_proximity(self,target,current=None):
        
        if current is None:
            current = self.drone_position

        if (
            (
                abs(current[0] - target[0])
                <= 0.000004517/3 #0.000004517
            )
            and (
                abs(current[1] - target[1])
                <= 0.0000047487/3 #0.0000047487
            )
            and (
                abs(current[2] - target[2])
                <= 0.2
            )
        ):
            # if self.iterations>=30:
            #     self.popped=False
            print("INSIDE PROXIMITY")
            print('self.target',target)
            print('self.dronepos',current)

            return True
            # else:
            #     self.iterations+=1
            #     return False
        else:
            # self.iterations = 0
            return False


    def check_proximity_with_iter(self,target,current=None):
        
        if current is None:
            current = self.drone_position

        if (
            (
                abs(current[0] - target[0])
                <= 0.000004517/3 #0.000004517
            )
            and (
                abs(current[1] - target[1])
                <= 0.0000047487/3 #0.0000047487
            )
            and (
                abs(current[2] - target[2])
                <= 0.2
            )
        ):
            if self.iterations>=50:
                
                print("INSIDE PROXIMITY")
                print('self.target',target)
                print('self.dronepos',current)

                return True
            else:
                self.iterations+=1
                return False
        else:
            self.iterations = 0
            return False


    def check_lat_long_proximity(self,target,current=None):
        
        if current is None:
            current = self.drone_position

        if (
            (
                abs(current[0] - target[0])<= 0.000004517*5 #0.000004517
            )
            and (
                abs(current[1] - target[1])<= 0.0000047487*5 #0.0000047487
            )
        ):  
            return True
        else:
            return False


    def range_finder_top_callback(self,msg):

        print('self.drone_orientation_euler[2]',self.drone_orientation_euler[2])
        if not self.avoiding:
            
            # print("NOT AVOIDING")
            self.top_sensor_dist=msg.ranges
            print('top sensor dist is',self.top_sensor_dist)
            if (any([self.top_sensor_dist[i]<=10 and self.top_sensor_dist[i]>=0.5 for i in range(5)])) and all(self.drone_position) and not self.check_lat_long_proximity(self.subs_setpoint):#or ((self.top_sensor_dist[3]<=25 and self.top_sensor_dist[3]>=0.5 )) :
                print(self.top_sensor_dist)
                
                #Checking if the obstacle is in the direction of motion
                if self.subs_setpoint[0]-self.drone_position[0]!=0:
                    print(self.subs_setpoint)
                    tan_theta=(self.subs_setpoint[1]-self.drone_position[1])/(self.subs_setpoint[0]-self.drone_position[0])
                    print('tan_theta',tan_theta)
                    theta=math.atan(tan_theta)
                else:
                    theta=9999999
                if abs(theta)>=2.3:
                    k=2
                    print("k=",k)
                elif theta<-1.3 and theta>-2.3:
                    k=1
                    print("k=",k)
                elif abs(theta)<=0.78:
                    k=0
                    print("k=",k)
                elif theta>0.78 and theta<2.3:
                    k=3
                    print("k=",k)
                else:
                    k='None'
                print('theta, k:',theta,k)

                if k=='None' or self.top_sensor_dist[k]<=10 and self.top_sensor_dist[k]>=0.45:
                    print("MAY DAY!!!!")
                    print(self.top_sensor_dist)
                    self.stop()
                    print("STOP")
                    self.avoiding=True
                    self.obstacle_detected_top=True
                
            else:
                self.obstacle_detected_top=False
        
        else:
            print("AVOIDING")
            print('self.drone_position',self.drone_position)
            print('self.avoiding_setpoint',self.avoiding_setpoint)
            self.bottom_obs.lat= self.avoiding_setpoint[0]
            self.bottom_obs.long=self.avoiding_setpoint[1]
            self.bottom_obs.alt=self.avoiding_setpoint[2]
            self.bottom_obs.obstacle_detected=True

            if self.check_proximity(self.avoiding_setpoint):
                self.avoiding=False


    def range_finder_bottom_callback(self,msg):

        self.bottom_sensor_dist=msg.ranges[0]
        if (self.bottom_sensor_dist<=2 and not self.parcel_picked and self.drone_position[2]!=0):
            self.obstacle_detected_bottom=True
            self.go_up()

        else:
            self.obstacle_detected_bottom=False
            self.go_up_counter=0
            # if not self.obs_detected():
            #     print("stopped up")
            #     pub_msg=destination()
            #     # pub_msg.lat=0
            #     # pub_msg.long=0
            #     # pub_msg.alt=0
            #     # pub_msg.obstacle_detected=False

            #     self.setpoint_pub.publish(pub_msg)
        self.check_gripper()

    def stop_at_current_pos_coords(self):
        x2=lat_to_x(self.drone_position[0])
        x1=lat_to_x(self.subs_setpoint[0])
        y2=long_to_y(self.drone_position[1])
        y1=long_to_y(self.subs_setpoint[1])
        print(self.drone_position)
        print(self.subs_setpoint)
        print('x2',x2,self.drone_position[0])
        print('x1',x1,self.subs_setpoint[0])
        print('y2',y2,self.drone_position[1])
        print('y1',y1,self.subs_setpoint[1])

        if x2==x1:
            x3=x2+1
            y3=y2
        else:
            m=(y2-y1)/(x2-x1)
            x3 = x2 - 50 * math.sqrt(1/(1+(m*m)))
            y3 = y2 + 50 *m * math.sqrt(1/(1+(m*m)))
        set_lat=x_to_lat(x3)
        set_long=y_to_long(y3)
        print('going to: x3',x3,set_lat)
        print('going to: y3',y3,set_long)
        
        return (set_lat,set_long)

    def stop_at_current_pos(self):
        if not self.current_pos_set:
            # TODO: use self.subs_setpoint & self.drone_position to get the coordinates of coordinate behind along the line of motion  
            coords=self.stop_at_current_pos_coords()
            self.top_obs.lat = coords[0]
            self.top_obs.long = coords[1]
            self.top_obs.alt = self.drone_position[2]
            self.top_obs.obstacle_detected=True
            self.avoiding_setpoint=[coords[0],coords[1],self.drone_position[2]]
            self.current_pos_set = True
            print("COORD SET")
        if self.check_proximity_with_iter(self.avoiding_setpoint):
            self.stopped_at_current_pos=True
            print("STOP successful!")


    def get_side_point(self):
        x2=lat_to_x(self.drone_position[0])
        x1=lat_to_x(self.last_point[0])
        y2=long_to_y(self.drone_position[1])
        y1=long_to_y(self.last_point[1])
        print(self.drone_position)
        print(self.last_point)
        print('x2',x2)
        print('x1',x1)
        print('y2',y2)
        print('y1',y1)

        if x2==x1:
            x3=x2+1
            y3=y2
        else:
            m=(y2-y1)/(x2-x1)
            x3 = x2 - 4 * m * math.sqrt(1/(1+(m*m)))
            y3 = y2 + 4 * math.sqrt(1/(1+(m*m)))
        print('x3',x3)
        print('y3',y3)
        set_lat=x_to_lat(x3)
        set_long=y_to_long(y3)
        
        return (set_lat,set_long)
        # return (19.000429913378706,72.00001)


    def stop(self):
 
        coords=self.get_side_point()
        print("")
        print("SIDE POINTS",coords,lat_to_x(coords[0]),long_to_y(coords[1]))
        print("current",self.drone_position,lat_to_x(self.drone_position[0]),long_to_y(self.drone_position[1]))
        self.top_obs.lat = coords[0]
        self.top_obs.long = coords[1]
        self.top_obs.alt = self.drone_position[2]
        self.top_obs.obstacle_detected=True
        self.avoiding_setpoint=[ coords[0] , coords[1] , self.drone_position[2] ]


    def obs_detected(self):
        return self.obstacle_detected_bottom or self.obstacle_detected_top


    def obs_avoid(self):
        if (self.drone_position[0]-self.last_point[0]>=0.00004517/4) or  (self.drone_position[1]-self.last_point[1]>=0.000047487/4) or  (self.drone_position[2]-self.last_point[2]>=0.1): 
            self.last_point=list(self.drone_position)

        if self.obstacle_detected_top:
            self.pub_msg=self.top_obs
            print("published",self.top_obs)
        elif self.obstacle_detected_bottom:
            self.pub_msg=self.bottom_obs
        else:
            self.pub_msg=destination()

    def reset(self):
        self.setpoint_pub.publish(destination())



def main():
    obs=Obstacle()
    r = rospy.Rate(50)
    rospy.on_shutdown(obs.reset)
    while not rospy.is_shutdown():
        print(time.strftime("%H:%M:%S"))
        if all(obs.drone_position):
            obs.obs_avoid()
        # else:
        #     obs.go_up_counter=0
        
        obs.setpoint_pub.publish(obs.pub_msg)
        r.sleep()


if __name__ == "__main__":
    main()

        