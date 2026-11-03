package worker;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.http.converter.json.JacksonJsonHttpMessageConverter;
import org.springframework.web.client.RestClient;

@Configuration 
public class RestClientConfig{
    @Bean
    public RestClient restClient(){
        return RestClient.builder()
            .requestFactory(new JdkClientHttpRequestFactory())
            .configureMessageConverters(converters -> converters.addCustomConverter(new JacksonJsonHttpMessageConverter()))
            .baseUrl("/internal/logic/games/")
            .build();
    }
}