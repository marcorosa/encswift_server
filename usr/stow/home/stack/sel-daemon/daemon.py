#!/usr/bin/env python

import os, sys, psutil, time, pika
from multiprocessing import Process
#from keystoneclient.v3 import client
#from keystoneclient import session
#from keystoneclient.auth import base
#from swift.proxy import server
import swiftclient
from keystoneclient.v2_0 import client as kc
import json

ADMIN_USER = 'admin'
ADMIN_PASS = 'secretsecret'
ADMIN_TENANT = 'admin'
AUTH_URL = 'http://localhost:5000/v2.0'


def new_cryptotoken(user,token):

    return encrypt(key=user,content=token)


def create_container(owner_cat):

    try:
        swift_conn.put_container(owner_cat, headers=None)
    except:
        sys.stderr.write('Error while putting container %s' % owner_cat)

    # Add ACL for this container
    ACL_headers = {}
    ACL_headers['x-container-read'] = owner_cat
    ACL_headers['x-container-write'] = UUID
    ACL_headers['x-container-meta-acl_label'] = owner_cat+':'+UUID
        
    try:
        swift_conn.post_container(owner_cat, headers=ACL_headers)
    except:
        sys.stderr.write('Error while setting the %s ACL_headers' % owner_cat)

    return


def get_graph(user):

    cat = swift_conn.get_object(container=user,obj=user)
    
    return load_graph(cat)
    

def insert_new_node(user,token,node):

    node[CRYPTOTOKEN] = new_cryptotoken(user,token)
     
    graph = get_graph(user)
    graph = remove_node(graph,node[NODE_CHILD])
    graph = add_node(graph,node,user,user)
    
    json = compose_graph(graph,user)    
  
    swift_conn.put_object(user,user,json)

    return


def delete_unnecessary_node(user,node,check):

    graph = get_graph(user)
    
    if check:
        f_node = get_node(graph,node[NODE_CHILD]) 
        if f_node == None:
            return None
    
    graph = remove_node(graph,node[NODE_CHILD])
    json = compose_graph(graph,user)
    swift_conn.put_object(user,user,json)
        
    return node[ACL_LIST]


def consumer_task():

    connection = pika.BlockingConnection(pika.ConnectionParameters(
               'localhost'))
    channel = connection.channel()
    channel.queue_declare(queue='daemon', durable=True)
           
    channel.basic_qos(prefetch_count=1)    
    channel.basic_consume(receive_message,
                      queue='daemon')

    print(' [%d] Waiting for messages...' % os.getpid())
    channel.start_consuming()


def receive_message(ch, method, properties, body):
        
    print(' [%d] Received' % os.getpid())
    command,sender_id,node = body.split('#')
    if command == 'CREATE':
        create_container(sender_id)    
    elif command == 'INSERT':
        list_usr = stringTOlist(node[ACL_LIST])
        token = node[CRYPTOTOKEN]
        for user_id in list_usr: 
            insert_new_node(user_id,token,node)
    elif command == 'REMOVE':
        acl_list = delete_unnecessary_node(sender_id,node,True)
        if acl_list != None:
            list_usr = stringTOlist(acl_list)
            list_usr.remove(sender_id)
            for user in list_usr:
                delete_unnecessary_node(user,node,False)
            
    print(' [%d] Done!' % os.getpid())
    ch.basic_ack(delivery_tag = method.delivery_tag)


def create_consumer(n,clist):
    
    for i in range(1,n):
        pid = os.fork()
        if pid:
            clist.append(pid)
        else: consumer_task()
        print ('             **** CREATED [%d] ****' % (pid))
    
    return


def kill_consumer(clist):

    i = 0

    for pid in clist:
        if i >= ctrlen/4:
            break
        proc = psutil.Process(pid)
        if proc.status == psutil.STATUS_SLEEPING:
            proc.kill()
            i += 1
            clist.remove(pid)
            print ('             **** DELETED IDLE [%d] ****' % (pid))

    return


def check_status():

    count = 0

    for pid in ctrl_list:
        proc = psutil.Process(pid)
        print(' PID [%d] status [%s]' % (pid, proc.status))
        if proc.status == psutil.STATUS_SLEEPING:
            count += 1
        elif proc.status == psutil.STATUS_RUNNING:
            count -= 1
        else: sys.stderr.write('Error on Process Status')

    return count


if __name__ == '__main__':

    swift_conn = swiftclient.client.Connection(
            user= ADMIN_USER, key= ADMIN_PASS, authurl= AUTH_URL,
            tenant_name= ADMIN_TENANT, auth_version='2.0')

    # Require an admin connection
    kc_conn = kc.Client(username=ADMIN_USER, password=ADMIN_PASS, tenant_name=ADMIN_TENANT, auth_url=AUTH_URL)
    this_user = filter(lambda x: x.username == ADMIN_USER, kc_conn.users.list())
    UUID = this_user[0].id   

    N_INI = 8
    ctrl_list = []

    create_consumer(N_INI+1,ctrl_list)

    while(True):

        count_sleep = check_status()

        ctrlen = len(ctrl_list)
        threshold = 3/4*ctrlen

        if count_sleep > threshold and count_sleep > N_INI:
            kill_consumer(ctrl_list)
        elif -count_sleep > ctrlen*3/4:
            create_consumer(ctrlen/2,ctrl_list)
        elif -count_sleep > ctrlen/2:
            create_consumer(ctrlen/3,ctrl_list)

        time.sleep(3)
    
    # never reached
  
