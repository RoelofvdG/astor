//JUnitOddEvenTest.java
import static org.junit.Assert.assertEquals;
import cardumenttest.OddEven;

public class JUnitOddEvenTest{

    @org.junit.Test
    public void test1() {
        OddEven o = new OddEven();
        assertEquals(false, o.isOdd(4));
    }
}