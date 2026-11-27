package worker;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
@EnableConfigurationProperties(WorkerProperties.class)
public class WorkerApplication{
	public static void main(String[] args){
		if(HealthProbe.requested(args)){
			System.exit(HealthProbe.run(System.getenv("PORT")));
		}
		SpringApplication.run(WorkerApplication.class, args);
	}
}
