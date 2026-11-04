package worker;

import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.http.converter.json.JacksonJsonHttpMessageConverter;
import org.springframework.web.client.RestClient;

/** Cliente HTTP hacia el gateway interno: GATEWAY_INTERNAL_URL es la URL base. */
@Configuration
public class RestClientConfig{

    static final Duration CONNECT_TIMEOUT = Duration.ofSeconds(3);
    static final Duration READ_TIMEOUT = Duration.ofSeconds(10);

    @Bean
    public RestClient restClient(WorkerProperties properties){
        return create(properties.gatewayInternalUrl());
    }

    static RestClient create(String baseUrl){
        HttpClient httpClient = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(CONNECT_TIMEOUT)
            .build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(httpClient);
        factory.setReadTimeout(READ_TIMEOUT);

        return RestClient.builder()
            .requestFactory(factory)
            .configureMessageConverters(converters -> converters.addCustomConverter(new JacksonJsonHttpMessageConverter()))
            .baseUrl(baseUrl)
            .build();
    }
}
