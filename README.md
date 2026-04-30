# SDN_IoT

################################################################################
date : 28 : Aprl: 2026
Install ryu if not from :https://github.com/faucetsdn/ryu.git 
------
Steps
--------

Step 1: In Terminal _1 

	cd ~/Documents/Learning_Mininet/LSTM_Code
	source ~/ryu_env/bin/activate
	ryu-manager ryu.app.simple_switch_13

	loading app ryu.app.simple_switch_13
	instantiating app simple_switch_13


once is done you need to deactivate 
 
Step 2 :In termina _2
	1. Running RunCode.sh 
		it runs: 
			Mqtt_Collector_rhy.py # rhy controller is used
			sensor_publisher.py 
			sensor_subscriber.py
			sensor_data_infinite.py  

		Collects Logs at:
			mqtt_capture
			tcpdump_data  
			pcap_captures  
step 3: python3 Pcap_To_csv_Summary.py # To Convert Pcap to csv 
				       # This intern call extract_pcap_to_csv.sh	
Learning points:

Brokers ip address hsould be  
	server = net.addHost('server', ip='10.0.0.100/8')
	BROKER_IP = "10.0.0.100"
mosquitto.conf file should have  
		
		
		

################################################################################
date : 11 : Aprl: 2026

Running RunCode.sh 
	it runs: 
		BaseCode_Mqtt_Collector.py
		sensor_publisher.py 
		sensor_subscriber.py
		sensor_data_infinite.py  

	Collects Logs at:
		mqtt_capture
		tcpdump_data  
		pcap_captures  
		
Learning points:

Brokers ip address hsould be  
	server = net.addHost('server', ip='10.0.0.100/8')
	BROKER_IP = "10.0.0.100"
mosquitto.conf file should have  
		
		
		
################################################################################

