package worker;

import java.util.List;
import java.util.Map;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class TimeoutService{
    public static final String TIMEOUT = "timeout";
    public static final String EXPIRED = "expired";
    public static final int TIMEOUT_BATCH_LIMIT = 100;

    private final RestClient restClient;

    public TimeoutService(RestClient restClient){
        this.restClient = restClient;
    }

    @Scheduled(fixedDelay = 5000)
    public void periodicallyTimeoutAndExpireMatches(){
        List<ExpiredQueryResponse> expiredMatchesInformation = restClient.get()
            .uri("expired?limit={N}", TIMEOUT_BATCH_LIMIT)
            .retrieve()
            .body(new ParameterizedTypeReference<List<ExpiredQueryResponse>>(){});

        for(ExpiredQueryResponse expiredMatch : expiredMatchesInformation){
            if(expiredMatch.reason().equals(TIMEOUT)){
                restClient.post()
                    .uri("{id}/timeout", expiredMatch.gameId())
                    .body(Map.of("expectedVersion", expiredMatch.version()));
            }else{
                restClient.post()
                    .uri("{id}/expire", expiredMatch.gameId())
                    .body(Map.of("expectedVersion", expiredMatch.version()));
            }
        }
    }
}
